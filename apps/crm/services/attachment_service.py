"""
Универсальный сервис для вложений.

Работает для ВСЕХ entities (любого типа).
"""

from datetime import UTC, datetime
from typing import cast as type_cast

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.models.crm_entity import CRMEntity, index_crm_entity
from apps.crm.services.crm_note_broadcast import broadcast_crm_note_event
from apps.crm.services.file_text_reader import load_text_from_bytes
from apps.crm.services.note_attachment_description import (
    merge_attachment_extracted_into_description,
)
from apps.crm.services.note_markdown_format_schedule import schedule_note_markdown_format
from core.authz.service import AuthzService
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import get_context
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.service import FilesService
from core.logging import get_logger
from core.rag import BaseRAGProvider
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)


class AttachmentService:
    """
    Универсальный сервис для вложений.

    Работает через entity_id (независимо от типа).
    """

    def __init__(
        self,
        rag: BaseRAGProvider,
        authz: AuthzService,
        files_service: FilesService,
    ) -> None:
        self._entity_rag: BaseRAGProvider = rag
        self._authz: AuthzService = authz
        self._files_service: FilesService = files_service
        self._rag: RagClient = RagClient()

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("No active company")
        return context.active_company.company_id

    @staticmethod
    def _as_json_object(value: JsonValue, context: str) -> JsonObject:
        return require_json_object(value, context)

    @staticmethod
    def _required_string(payload: JsonObject, key: str, context: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(f"{context}.{key} must be a non-empty string")
        return value

    @staticmethod
    def _optional_string(value: JsonValue) -> str | None:
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
        return None

    async def add_attachment(
        self,
        entity_id: str,
        file_id: str,
    ) -> JsonObject:
        """Привязывает уже загруженный FileRecord к entity."""
        cleaned_file_id = file_id.strip()
        if cleaned_file_id == "":
            raise ValueError("file_id is required")

        context = get_context()
        if context is None:
            raise ValueError("No request context")
        company_id = self._get_company_id()

        entity = await CRMEntity.get(entity_id)

        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        namespace = entity.namespace.strip()
        if namespace == "":
            raise ValueError(f"Entity {entity_id} has empty namespace")
        record = await self._files_service.get(cleaned_file_id)
        if record.company_id != company_id:
            raise ValueError(f"file {cleaned_file_id} belongs to another company")

        filename = record.original_name
        metadata: JsonObject = {
            "entity_id": entity_id,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype or "",
            "company_id": company_id,
            "filename": filename,
            "ttl_seconds": 0,
        }

        document_id = record.file_id

        index_response = self._as_json_object(
            type_cast(
                JsonValue,
                await self._rag.index_file(
                    namespace,
                    document_id,
                    metadata=metadata,
                    document_name=filename,
                ),
            ),
            "RAG index_file response",
        )

        if document_id not in entity.attachment_ids:
            entity.attachment_ids.append(document_id)

        attachment_had_extractable_text = False
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            file_data = await self._download_file_bytes(record)
            try:
                raw_text = await load_text_from_bytes(file_data, filename)
            except Exception as exc:
                logger.warning(
                    "crm.note.attachment.text.extract.failed",
                    entity_id=entity_id,
                    filename=filename,
                    error=str(exc),
                )
                raw_text = ""
            attachment_had_extractable_text = bool(raw_text.strip())
            entity.description = merge_attachment_extracted_into_description(
                entity.description,
                filename,
                raw_text,
            )

        entity.updated_at = datetime.now(UTC)
        merged = await CRMEntity.update_loaded(entity)
        await index_crm_entity(self._entity_rag, merged, replace=True)
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            note_date_iso = merged.note_date.isoformat() if merged.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=merged.company_id,
                namespace=merged.namespace,
                note_id=merged.entity_id,
                note_date_iso=note_date_iso,
                action="updated",
                note=merged,
                authz=self._authz,
            )

        markdown_format_queued = False
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID and attachment_had_extractable_text:
            markdown_format_queued = await schedule_note_markdown_format(
                authz=self._authz,
                note_id=entity_id,
                company_id=company_id,
                namespace=namespace,
            )

        logger.info(
            "crm.attachment.added.type.doc_id",
            filename=filename,
            entity_id=entity_id,
            type_value=entity.full_type,
            doc_id=document_id,
        )

        status = index_response.get("status")
        if not isinstance(status, str) or status.strip() == "":
            raise ValueError("RAG index_file response.status required")
        task_id = index_response.get("task_id")
        if task_id is not None and not isinstance(task_id, str):
            raise ValueError("RAG index_file response.task_id must be string")
        return {
            "document_id": document_id,
            "filename": filename,
            "status": status,
            "task_id": task_id,
            "markdown_format_queued": markdown_format_queued,
        }

    async def _download_file_bytes(self, record: FileRecord) -> bytes:
        if record.storage_id == "" or record.s3_key == "":
            raise ValueError(f"file {record.file_id} has no storage location")
        if record.company_id is None or record.company_id == "":
            raise ValueError(f"file {record.file_id} has no company_id")
        handle = await FileGate().open_record(
            record,
            SystemPrincipal(company_id=record.company_id),
        )
        return await handle.read_bytes()


    async def remove_attachment(
        self,
        entity_id: str,
        document_id: str,
    ) -> None:
        context = get_context()
        if context is None:
            raise ValueError("No request context")

        entity = await CRMEntity.get(entity_id)

        if entity is None or document_id not in entity.attachment_ids:
            raise LookupError(f"Attachment not found: {document_id} for {entity_id}")

        namespace = entity.namespace.strip()
        if namespace == "":
            raise ValueError(f"Entity {entity_id} has empty namespace")
        _ = await self._rag.delete_namespace_document(namespace, document_id)

        entity.attachment_ids.remove(document_id)
        entity.updated_at = datetime.now(UTC)
        entity = await CRMEntity.update_loaded(entity)
        await index_crm_entity(self._entity_rag, entity, replace=True)
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            note_date_iso = entity.note_date.isoformat() if entity.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=entity.company_id,
                namespace=entity.namespace,
                note_id=entity.entity_id,
                note_date_iso=note_date_iso,
                action="updated",
                note=entity,
                authz=self._authz,
            )

        logger.info("crm.attachment.removed", document_id=document_id, entity_id=entity_id)

    async def get_attachments(
        self,
        entity_id: str,
    ) -> list[JsonObject]:
        """Получает список attachments entity"""
        entity = await CRMEntity.get(entity_id)

        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        if not entity.attachment_ids:
            return []

        attachments: list[JsonObject] = []
        for doc_id in entity.attachment_ids:
            file_record = await FileRecord.get(doc_id)
            if file_record is not None:
                attachments.append(
                    {
                        "document_id": doc_id,
                        "filename": file_record.original_name,
                        "status": file_record.status.value,
                        "metadata": self._as_json_object(
                            type_cast(JsonValue, file_record.metadata),
                            "file metadata",
                        ),
                        "size_bytes": file_record.file_size,
                        "content_type": file_record.content_type,
                        "download_url": file_record.url,
                    }
                )
                continue

            try:
                response = await self._rag.get_document_processing_status(doc_id)
            except (ServiceClientError, ValueError) as exc:
                logger.warning(
                    "crm.attachment.status.missing.file.storage",
                    entity_id=entity_id,
                    document_id=doc_id,
                    error=str(exc),
                )
                attachments.append(
                    {
                        "document_id": doc_id,
                        "filename": "missing",
                        "status": "missing",
                        "metadata": {"orphaned_attachment": True},
                        "size_bytes": 0,
                        "content_type": "",
                        "download_url": "",
                    }
                )
                continue
            response = self._as_json_object(type_cast(JsonValue, response), "RAG status response")
            display_name = response.get("filename") or response.get("document_name")
            extra = response.get("extra_metadata")
            extra_metadata: JsonObject = {}
            if isinstance(extra, dict):
                extra_metadata = self._as_json_object(
                    type_cast(JsonValue, extra),
                    "RAG status extra_metadata",
                )
            if not isinstance(display_name, str) or display_name.strip() == "":
                display_name = self._optional_string(extra_metadata.get("filename"))
            if display_name is None:
                display_name = "unknown"
            else:
                display_name = display_name.strip()

            size_bytes = response.get("size_bytes")
            if not isinstance(size_bytes, int):
                candidate_size = extra_metadata.get("size_bytes")
                if isinstance(candidate_size, int):
                    size_bytes = candidate_size

            content_type = self._optional_string(extra_metadata.get("content_type"))

            attachments.append(
                {
                    "document_id": doc_id,
                    "filename": display_name,
                    "status": response.get("status", "unknown"),
                    "metadata": extra_metadata,
                    "size_bytes": size_bytes if isinstance(size_bytes, int) else 0,
                    "content_type": content_type or "",
                    "download_url": RagClient.files_download_url_path(doc_id),
                }
            )

        return attachments

    async def delete_all_attachments(
        self,
        entity_id: str,
    ) -> int:
        """Удаляет все attachments entity (для каскадного удаления)"""
        entity = await CRMEntity.get(entity_id)

        if not entity or not entity.attachment_ids:
            return 0

        deleted_count = 0

        for doc_id in list(entity.attachment_ids):
            await self.remove_attachment(entity_id, doc_id)
            deleted_count += 1

        logger.info("crm.attachment.deleted_for_entity", entity_id=entity_id, deleted_count=deleted_count)
        return deleted_count

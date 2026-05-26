"""
Универсальный сервис для вложений.

Работает для ВСЕХ entities (любого типа).
"""

from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from typing import cast as type_cast

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm.services.file_text_reader import load_text_from_bytes
from apps.crm.services.note_attachment_description import (
    merge_attachment_extracted_into_description,
)
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import get_context
from core.logging import get_logger
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from apps.crm.db.repositories.entity_repository import EntityRepository
    from core.db.repositories import CompanyRepository
    from core.files.file_repository import FileRepository

logger = get_logger(__name__)


class NoteMarkdownFormatScheduler(Protocol):
    def __call__(
        self,
        *,
        note_id: str,
        company_id: str,
        namespace: str,
        expected_updated_at_iso: str,
    ) -> Awaitable[bool]: ...


class AttachmentService:
    """
    Универсальный сервис для вложений.

    Работает через entity_id (независимо от типа).
    """

    def __init__(
        self,
        entity_repository: "EntityRepository",
        access_grant_repository: "AccessGrantRepository",
        company_repository: "CompanyRepository",
        file_repository: "FileRepository",
        note_markdown_format_scheduler: NoteMarkdownFormatScheduler,
    ) -> None:
        self._rag: RagClient = RagClient()
        self._entity_repo: EntityRepository = entity_repository
        self._access_grant_repo: AccessGrantRepository = access_grant_repository
        self._company_repo: CompanyRepository = company_repository
        self._file_repo: FileRepository = file_repository
        self._note_markdown_format_scheduler: NoteMarkdownFormatScheduler = (
            note_markdown_format_scheduler
        )

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании")
        return context.active_company.company_id

    @staticmethod
    def _as_json_object(value: object, context: str) -> JsonObject:
        return require_json_object(value, context)

    @staticmethod
    def _required_string(payload: JsonObject, key: str, context: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(f"{context}.{key} must be a non-empty string")
        return value

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
        return None

    async def add_attachment(
        self,
        entity_id: str,
        file_data: bytes,
        filename: str,
    ) -> JsonObject:
        """Загружает attachment для entity"""
        context = get_context()
        if context is None:
            raise ValueError("Нет контекста запроса")
        company_id = self._get_company_id()
        namespace_name = context.active_namespace

        entity = await self._entity_repo.get(entity_id)

        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        namespace = namespace_name

        metadata: JsonObject = {
            "entity_id": entity_id,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype or "",
            "company_id": company_id,
            "filename": filename,
            "ttl_seconds": 0,
        }

        response = self._as_json_object(
            type_cast(
                object,
                await self._rag.upload_namespace_document(
                    namespace,
                    filename=filename,
                    file_bytes=file_data,
                    metadata=metadata,
                ),
            ),
            "RAG upload response",
        )

        document_id = self._required_string(response, "document_id", "RAG upload response")

        if document_id not in entity.attachment_ids:
            entity.attachment_ids.append(document_id)

        attachment_had_extractable_text = False
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            try:
                raw_text = await load_text_from_bytes(file_data, filename)
            except Exception as exc:
                logger.warning(
                    "note attachment: text extract failed",
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
        merged = await self._entity_repo.update(entity)
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            note_date_iso = merged.note_date.isoformat() if merged.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=merged.company_id,
                namespace=merged.namespace,
                note_id=merged.entity_id,
                note_date_iso=note_date_iso,
                action="updated",
                company_repository=self._company_repo,
                access_grant_repository=self._access_grant_repo,
            )

        markdown_format_queued = False
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID and attachment_had_extractable_text:
            markdown_format_queued = await self._note_markdown_format_scheduler(
                note_id=entity_id,
                company_id=company_id,
                namespace=namespace,
                expected_updated_at_iso=merged.updated_at.isoformat(),
            )

        logger.info(
            "Attachment added: %s -> %s (type=%s), doc_id=%s",
            filename,
            entity_id,
            entity.full_type,
            document_id,
        )

        return {
            "document_id": document_id,
            "filename": filename,
            "status": response.get("status", "unknown"),
            "task_id": response.get("task_id"),
            "markdown_format_queued": markdown_format_queued,
        }

    async def remove_attachment(
        self,
        entity_id: str,
        document_id: str,
    ) -> bool:
        """Удаляет attachment entity"""
        context = get_context()
        if context is None:
            raise ValueError("Нет контекста запроса")
        namespace_name = context.active_namespace

        entity = await self._entity_repo.get(entity_id)

        if not entity or document_id not in entity.attachment_ids:
            logger.warning(f"Attachment not found: {document_id} for {entity_id}")
            return False

        _ = await self._rag.delete_namespace_document(namespace_name, document_id)

        entity.attachment_ids.remove(document_id)
        entity.updated_at = datetime.now(UTC)
        _ = await self._entity_repo.update(entity)
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            note_date_iso = entity.note_date.isoformat() if entity.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=entity.company_id,
                namespace=entity.namespace,
                note_id=entity.entity_id,
                note_date_iso=note_date_iso,
                action="updated",
                company_repository=self._company_repo,
                access_grant_repository=self._access_grant_repo,
            )

        logger.info(f"Attachment removed: {document_id} from {entity_id}")
        return True

    async def get_attachments(
        self,
        entity_id: str,
    ) -> list[JsonObject]:
        """Получает список attachments entity"""
        entity = await self._entity_repo.get(entity_id)

        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        if not entity.attachment_ids:
            return []

        attachments: list[JsonObject] = []
        for doc_id in entity.attachment_ids:
            file_record = await self._file_repo.get(doc_id)
            if file_record is not None:
                attachments.append(
                    {
                        "document_id": doc_id,
                        "filename": file_record.original_name,
                        "status": file_record.status.value,
                        "metadata": self._as_json_object(
                            type_cast(object, file_record.metadata),
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
                    "Attachment status missing in file storage and rag status endpoint",
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
            response = self._as_json_object(type_cast(object, response), "RAG status response")
            display_name = response.get("filename") or response.get("document_name")
            extra = response.get("extra_metadata")
            extra_metadata: JsonObject = {}
            if isinstance(extra, dict):
                extra_metadata = self._as_json_object(
                    type_cast(object, extra),
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
        entity = await self._entity_repo.get(entity_id)

        if not entity or not entity.attachment_ids:
            return 0

        deleted_count = 0

        for doc_id in list(entity.attachment_ids):
            try:
                success = await self.remove_attachment(entity_id, doc_id)
                if success:
                    deleted_count += 1
            except (ServiceClientError, ValueError) as e:
                logger.error(
                    "Failed to delete attachment",
                    entity_id=entity_id,
                    document_id=doc_id,
                    error=str(e),
                )

        logger.info(f"Deleted {deleted_count} attachments for {entity_id}")
        return deleted_count

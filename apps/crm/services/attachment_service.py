"""
Универсальный сервис для вложений.

Работает для ВСЕХ entities (любого типа).
"""

from typing import Dict, Any, List, TYPE_CHECKING
from datetime import datetime, timezone
from io import BytesIO
import json

from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import get_context
from core.logging import get_logger
from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event

if TYPE_CHECKING:
    from apps.crm.db.repositories.entity_repository import EntityRepository
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from core.db.repositories import CompanyRepository
    from core.files.file_repository import FileRepository

logger = get_logger(__name__)


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
    ):
        self._service_client = ServiceClient()
        self._entity_repo = entity_repository
        self._access_grant_repo = access_grant_repository
        self._company_repo = company_repository
        self._file_repo = file_repository
    
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании")
        return context.active_company.company_id
    
    async def add_attachment(
        self,
        entity_id: str,
        file_data: bytes,
        filename: str,
        
    ) -> Dict[str, Any]:
        """Загружает attachment для entity"""
        context = get_context()
        company_id = self._get_company_id()
        namespace_name = context.active_namespace
        
        entity = await self._entity_repo.get(entity_id)
        
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        namespace = namespace_name
        
        metadata = {
            "entity_id": entity_id,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype or "",
            "company_id": company_id,
            "filename": filename,
            "ttl_seconds": 0,
        }
        
        files = {"file": (filename, BytesIO(file_data), "application/octet-stream")}
        
        response = await self._service_client.post(
            service="rag",
            path=f"/rag/api/v1/namespaces/{namespace}/documents",
            files=files,
            data={"metadata": json.dumps(metadata)}
        )
        
        document_id = response["document_id"]
        
        if document_id not in entity.attachment_ids:
            entity.attachment_ids.append(document_id)
        
        entity.updated_at = datetime.now(timezone.utc)
        await self._entity_repo.update(entity)
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
        
        logger.info(
            f"Attachment added: {filename} -> {entity_id} "
            f"(type={entity.full_type}), doc_id={document_id}"
        )
        
        return {
            "document_id": document_id,
            "filename": filename,
            "status": response["status"],
            "task_id": response.get("task_id")
        }
    
    async def remove_attachment(
        self,
        entity_id: str,
        document_id: str,
        
    ) -> bool:
        """Удаляет attachment entity"""
        context = get_context()
        namespace_name = context.active_namespace
        
        entity = await self._entity_repo.get(entity_id)
        
        if not entity or document_id not in entity.attachment_ids:
            logger.warning(f"Attachment not found: {document_id} for {entity_id}")
            return False
        
        await self._service_client.delete(
            service="rag",
            path=f"/rag/api/v1/namespaces/{namespace_name}/documents/{document_id}"
        )
        
        entity.attachment_ids.remove(document_id)
        entity.updated_at = datetime.now(timezone.utc)
        await self._entity_repo.update(entity)
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
        
    ) -> List[Dict[str, Any]]:
        """Получает список attachments entity"""
        entity = await self._entity_repo.get(entity_id)
        
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        if not entity.attachment_ids:
            return []
        
        attachments = []
        for doc_id in entity.attachment_ids:
            file_record = await self._file_repo.get(doc_id)
            if file_record is not None:
                attachments.append({
                    "document_id": doc_id,
                    "filename": file_record.original_name,
                    "status": file_record.status.value,
                    "metadata": file_record.metadata,
                    "size_bytes": file_record.file_size,
                    "content_type": file_record.content_type,
                    "download_url": file_record.url,
                })
                continue

            try:
                response = await self._service_client.get(
                    service="rag",
                    path=f"/rag/api/v1/documents/{doc_id}/status"
                )
            except ServiceClientError as exc:
                logger.warning(
                    "Attachment status missing in file storage and rag status endpoint",
                    entity_id=entity_id,
                    document_id=doc_id,
                    error=str(exc),
                )
                attachments.append({
                    "document_id": doc_id,
                    "filename": "missing",
                    "status": "missing",
                    "metadata": {"orphaned_attachment": True},
                    "size_bytes": 0,
                    "content_type": "",
                    "download_url": "",
                })
                continue
            if not isinstance(response, dict):
                raise ValueError(f"RAG document status must be dict, got {type(response)}")
            display_name = (
                response.get("filename")
                or response.get("document_name")
            )
            extra = response.get("extra_metadata")
            if not display_name and isinstance(extra, dict):
                candidate = extra.get("filename")
                if isinstance(candidate, str) and candidate.strip():
                    display_name = candidate.strip()
            if not display_name:
                display_name = "unknown"

            size_bytes = response.get("size_bytes")
            if not isinstance(size_bytes, int) and isinstance(extra, dict):
                candidate_size = extra.get("size_bytes")
                if isinstance(candidate_size, int):
                    size_bytes = candidate_size

            content_type = None
            if isinstance(extra, dict):
                candidate_type = extra.get("content_type")
                if isinstance(candidate_type, str):
                    content_type = candidate_type

            attachments.append({
                "document_id": doc_id,
                "filename": display_name,
                "status": response.get("status", "unknown"),
                "metadata": extra if isinstance(extra, dict) else {},
                "size_bytes": size_bytes if isinstance(size_bytes, int) else 0,
                "content_type": content_type if isinstance(content_type, str) else "",
                "download_url": f"/rag/api/v1/files/download/{doc_id}",
            })
        
        return attachments
    
    async def delete_all_attachments(
        self,
        entity_id: str
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
            except Exception as e:
                logger.error(f"Failed to delete attachment {doc_id} for {entity_id}: {e}")
        
        logger.info(f"Deleted {deleted_count} attachments for {entity_id}")
        return deleted_count

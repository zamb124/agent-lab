"""
Универсальный сервис для вложений.

Работает для ВСЕХ entities (любого типа).
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from io import BytesIO
import json

from core.clients.service_client import ServiceClient
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)


class AttachmentService:
    """
    Универсальный сервис для вложений.
    
    Работает через entity_id (независимо от типа).
    """
    
    def __init__(self):
        self._service_client = ServiceClient()
    
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании")
        return context.active_company.company_id
    
    def _get_entity_repo(self):
        """Получает EntityChromaRepository из контейнера"""
        from apps.crm.container import get_crm_container
        
        container = get_crm_container()
        return container.entity_repository
    
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
        
        repo = self._get_entity_repo()
        entity = await repo.get(entity_id)
        
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        # Используем только namespace_name, RAG сервис сам добавит company_id
        namespace = namespace_name
        
        metadata = {
            "entity_id": entity_id,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype or "",
            "company_id": company_id,
            "filename": filename
        }
        
        files = {"file": (filename, BytesIO(file_data), "application/octet-stream")}
        
        # RAG API ожидает metadata как Form field
        # При передаче files httpx автоматически установит multipart/form-data
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
        await repo.update(entity)
        
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
        company_id = self._get_company_id()
        namespace_name = context.active_namespace
        
        repo = self._get_entity_repo()
        entity = await repo.get(entity_id)
        
        if not entity or document_id not in entity.attachment_ids:
            logger.warning(f"Attachment not found: {document_id} for {entity_id}")
            return False
        
        await self._service_client.delete(
            service="rag",
            path=f"/rag/api/v1/namespaces/{namespace_name}/documents/{document_id}"
        )
        
        entity.attachment_ids.remove(document_id)
        entity.updated_at = datetime.now(timezone.utc)
        await repo.update(entity)
        
        logger.info(f"Attachment removed: {document_id} from {entity_id}")
        return True
    
    async def get_attachments(
        self,
        entity_id: str,
        
    ) -> List[Dict[str, Any]]:
        """Получает список attachments entity"""
        context = get_context()
        company_id = self._get_company_id()
        namespace_name = context.active_namespace
        
        repo = self._get_entity_repo()
        entity = await repo.get(entity_id)
        
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        if not entity.attachment_ids:
            return []
        
        attachments = []
        for doc_id in entity.attachment_ids:
            try:
                response = await self._service_client.get(
                    service="rag",
                    path=f"/rag/api/v1/documents/{doc_id}/status"
                )
                
                attachments.append({
                    "document_id": doc_id,
                    "filename": response.get("filename", "unknown"),
                    "status": response.get("status", "unknown"),
                    "metadata": response.get("metadata", {})
                })
            except Exception as e:
                logger.warning(f"Failed to get attachment info: {doc_id}, error: {e}")
                attachments.append({
                    "document_id": doc_id,
                    "filename": "unknown",
                    "status": "error",
                    "metadata": {}
                })
        
        return attachments
    
    async def delete_all_attachments(
        self,
        entity_id: str
    ) -> int:
        """Удаляет все attachments entity (для каскадного удаления)"""
        repo = self._get_entity_repo()
        entity = await repo.get(entity_id)
        
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


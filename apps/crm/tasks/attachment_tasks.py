"""
TaskIQ задачи для обработки CRM attachments и импорта файлов.

Attachments загружаются в S3 синхронно, затем асинхронно индексируются в RAG.
Импорт файлов - парсинг документа и создание заметки асинхронно.
"""

import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, Optional, List

from core.tasks.broker import broker
from core.rag.factory import get_default_rag_provider
from core.rag import DocumentParser
from core.websocket import websocket_manager

logger = logging.getLogger(__name__)

# Namespace prefix для CRM attachments
CRM_ATTACHMENTS_NAMESPACE = "crm_attachments"


def _get_namespace(company_id: str) -> str:
    """Формирует namespace для компании"""
    return f"{CRM_ATTACHMENTS_NAMESPACE}_{company_id}"


@broker.task(retry_on_error=True, max_retries=3)
async def process_crm_attachment_task(
    company_id: str,
    note_id: str,
    file_id: str,
    s3_key: str,
    document_name: str,
    content_type: str,
    note_title: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Асинхронная индексация attachment в RAG.
    
    Вызывается после загрузки файла в S3.
    Если формат поддерживается - парсит документ, делает chunking и embedding.
    Если нет - просто сохраняет как uploaded (без индексации).
    """
    namespace = _get_namespace(company_id)
    logger.info(f"CRM RAG: начало обработки attachment {file_id} в namespace {namespace}")
    
    # Проверяем, поддерживается ли формат для индексации
    parser = DocumentParser()
    if not parser.is_supported(document_name):
        logger.info(f"CRM RAG: формат файла {document_name} не поддерживается для индексации, пропускаем")
        notification = {
            "type": "CRM_ATTACHMENT_UPLOADED",
            "data": {
                "file_id": file_id,
                "note_id": note_id,
                "document_name": document_name,
                "status": "uploaded",
                "indexed": False,
                "reason": "unsupported_format",
            },
        }
        await websocket_manager.publish_to_redis(notification, "notifications")
        return {
            "status": "uploaded",
            "file_id": file_id,
            "indexed": False,
        }
    
    provider = get_default_rag_provider()
    
    document = await provider.upload_document_from_s3(
        namespace_id=namespace,
        s3_key=s3_key,
        document_name=document_name,
        metadata={
            "file_id": file_id,
            "note_id": note_id,
            "note_title": note_title or "",
            "content_type": content_type,
            "company_id": company_id,
        },
    )
    
    logger.info(f"CRM RAG: attachment {file_id} проиндексирован, document_id={document.document_id}")
    
    notification = {
        "type": "CRM_ATTACHMENT_INDEXED",
        "data": {
            "file_id": file_id,
            "note_id": note_id,
            "document_id": document.document_id,
            "document_name": document_name,
            "status": "completed",
        },
    }
    await websocket_manager.publish_to_redis(notification, "notifications")
    
    return {
        "status": "completed",
        "file_id": file_id,
        "document_id": document.document_id,
        "indexed": True,
    }


@broker.task(retry_on_error=True, max_retries=3)
async def delete_crm_attachment_task(
    company_id: str,
    note_id: str,
    file_id: str,
    s3_key: str,
) -> Dict[str, Any]:
    """
    Удаляет attachment из RAG и S3.
    """
    from core.files.s3_client import S3ClientFactory
    
    namespace = _get_namespace(company_id)
    logger.info(f"CRM: удаление attachment {file_id}")
    
    # Удаляем из RAG
    provider = get_default_rag_provider()
    deleted_from_rag = await provider.delete_document(namespace, file_id)
    
    # Удаляем из S3 напрямую
    s3_client = S3ClientFactory.create_default_client()
    deleted_from_s3 = await s3_client.delete_file(s3_key)
    await s3_client.close()
    
    notification = {
        "type": "CRM_ATTACHMENT_DELETED",
        "data": {
            "file_id": file_id,
            "note_id": note_id,
            "deleted_from_rag": deleted_from_rag,
            "deleted_from_s3": deleted_from_s3,
        },
    }
    await websocket_manager.publish_to_redis(notification, "notifications")
    
    return {
        "status": "completed",
        "file_id": file_id,
        "deleted_from_rag": deleted_from_rag,
        "deleted_from_s3": deleted_from_s3,
    }


@broker.task(retry_on_error=True, max_retries=3)
async def delete_note_attachments_task(
    company_id: str,
    note_id: str,
    attachments: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Удаляет все attachments заметки из RAG и S3.
    Вызывается при удалении заметки.
    
    Args:
        attachments: список dict с file_id и s3_key
    """
    from core.files.s3_client import S3ClientFactory
    
    namespace = _get_namespace(company_id)
    logger.info(f"CRM: удаление {len(attachments)} attachments заметки {note_id}")
    
    provider = get_default_rag_provider()
    s3_client = S3ClientFactory.create_default_client()
    
    results = []
    
    for attachment in attachments:
        file_id = attachment.get("file_id")
        s3_key = attachment.get("s3_key")
        if not file_id or not s3_key:
            continue
        
        deleted_from_rag = await provider.delete_document(namespace, file_id)
        deleted_from_s3 = await s3_client.delete_file(s3_key)
        
        results.append({
            "file_id": file_id,
            "deleted_from_rag": deleted_from_rag,
            "deleted_from_s3": deleted_from_s3,
        })
    
    await s3_client.close()
    logger.info(f"CRM: удалено {len(results)} attachments заметки {note_id}")
    
    return {
        "status": "completed",
        "note_id": note_id,
        "attachments_deleted": results,
    }


@broker.task(retry_on_error=True, max_retries=3)
async def import_note_from_file_task(
    note_id: str,
    company_id: str,
    user_id: str,
    file_id: str,
    s3_key: str,
    filename: str,
    title: str,
    note_type: str,
    note_date: str,
) -> Dict[str, Any]:
    """
    Асинхронный парсинг файла и обновление заметки.
    
    Заметка создается со статусом 'importing', таска парсит файл
    и обновляет content заметки.
    """
    from apps.crm.db.repositories.note_repository import NoteRepository
    from core.config import get_settings
    from core.files.s3_client import S3ClientFactory
    
    logger.info(f"CRM: парсинг файла {filename} для заметки {note_id}")
    
    # Скачиваем файл напрямую из S3
    s3_client = S3ClientFactory.create_default_client()
    file_bytes = await s3_client.download_bytes(s3_key)
    await s3_client.close()
    
    # Парсим документ
    parser = DocumentParser()
    content = parser.parse_bytes(file_bytes, filename)
    
    # Обновляем заметку через CRMDatabase
    from apps.crm.db.base import CRMDatabase
    settings = get_settings()
    
    crm_db = CRMDatabase(settings.database.crm_url)
    repo = NoteRepository(crm_db)
    
    note = await repo.get(note_id)
    if note:
        note.content = content
        note.status = "draft"
        note.updated_at = datetime.now(timezone.utc)
        await repo.update(note)
    
    logger.info(f"CRM: заметка {note_id} импортирована из {filename}")
    
    # Уведомление
    notification = {
        "type": "CRM_NOTE_IMPORTED",
        "data": {
            "note_id": note_id,
            "title": title,
            "filename": filename,
            "status": "completed",
        },
    }
    await websocket_manager.publish_to_redis(notification, "notifications")
    
    return {
        "status": "completed",
        "note_id": note_id,
        "content_length": len(content),
    }

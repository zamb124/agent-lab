"""
API для управления документами.
"""

import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from apps.chroma_worker.tasks.indexing_tasks import upload_document_task
import uuid
from core.logging import get_logger
from core.rag.models import RAGDocument
from core.rag.factory import get_rag_provider
from core.config import get_settings
from core.files.s3_client import build_s3_key_from_context
from ..container import RAGContainer
from ..dependencies import get_container_dep

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])


class DocumentListResponse(BaseModel):
    """Ответ со списком документов"""
    documents: List[RAGDocument]
    namespace_id: str
    provider: str


class DocumentUploadResponse(BaseModel):
    """Ответ на загрузку документа (асинхронный)"""
    document_id: str
    task_id: str
    status: str
    message: str


@router.get("/namespaces/{namespace_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    namespace_id: str,
    limit: int = Query(100, ge=1, le=1000),
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep)
) -> DocumentListResponse:
    """
    Получает список документов в namespace.
    
    Объединяет данные из:
    - ChromaDB (completed документы)
    - document_processing_status (pending/processing/failed)
    
    Args:
        namespace_id: ID namespace
        limit: Максимальное количество документов
        provider: Имя провайдера (опционально)
    
    Returns:
        Список документов со статусами
    """

    
    settings = get_settings()
    
    try:
        rag_provider = get_rag_provider(provider) if provider else container.rag_provider
        provider_name = provider or settings.rag.default_provider
        
        completed_docs = await rag_provider.list_documents(namespace_id, limit=limit)
        
        status_repo = container.document_status_repository
        processing_statuses = await status_repo.list_by_namespace(
            namespace_id,
            status=["pending", "processing", "failed"],
            limit=limit
        )
        
        all_documents = []
        
        for doc in completed_docs:
            all_documents.append(doc)
        
        for status in processing_statuses:
            doc = RAGDocument(
                document_id=status.document_id,
                name=status.document_name,
                namespace=status.namespace_id,
                status=status.status,
                metadata={
                    "file_size": status.file_size,
                    "error_message": status.error_message,
                    "task_id": status.task_id,
                    "created_at": status.created_at.isoformat(),
                    "updated_at": status.updated_at.isoformat()
                }
            )
            all_documents.append(doc)
        
        logger.info(f"Получено {len(all_documents)} документов из namespace {namespace_id} ({len(completed_docs)} completed, {len(processing_statuses)} processing)")
        
        return DocumentListResponse(
            documents=all_documents[:limit],
            namespace_id=namespace_id,
            provider=provider_name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка получения документов: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.post("/namespaces/{namespace_id}/documents", status_code=202, response_model=DocumentUploadResponse)
async def upload_document(
    namespace_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep)
) -> DocumentUploadResponse:
    """
    Запускает асинхронную загрузку документа.
    
    Args:
        namespace_id: ID namespace
        file: Файл для загрузки
        metadata: JSON string с метаданными документа
        provider: Имя провайдера (опционально)
    
    Returns:
        202 Accepted с task_id для отслеживания статуса
    """

    
    try:
        metadata_dict: Dict[str, Any] = json.loads(metadata) if metadata else {}
        
        document_id = str(uuid.uuid4())
        file_data = await file.read()
        
        # Получаем единый S3 клиент
        s3_client = await container.get_s3_client()
        if not s3_client:
            raise HTTPException(status_code=500, detail="S3 не настроен")
        
        # Строим ключ с префиксом компании из контекста
        
        s3_key = build_s3_key_from_context(
            f"rag/{namespace_id}/{document_id}/{file.filename}"
        )
        
        await s3_client.upload_bytes(
            data=file_data,
            key=s3_key,
            content_type=file.content_type
        )
        
        status_repo = container.document_status_repository
        
        # Создаем статус ДО отправки задачи
        task_id_placeholder = f"task_{document_id}"
        await status_repo.create_status(
            document_id=document_id,
            task_id=task_id_placeholder,
            namespace_id=namespace_id,
            document_name=file.filename,
            file_size=len(file_data)
        )
        
        # Добавляем document_id в metadata для ChromaDB
        metadata_dict["document_id"] = document_id
        
        # Отправляем задачу на индексацию с s3_key (не с file_data!)
        task = await upload_document_task.kiq(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=file.filename,
            metadata=metadata_dict
        )
        
        # Task ID уже установлен при создании
        
        logger.info(f"Документ {file.filename} принят на обработку: doc_id={document_id}, task_id={task.task_id}, s3_key={s3_key}")
        
        return DocumentUploadResponse(
            document_id=document_id,
            task_id=task.task_id,
            status="pending",
            message="Document upload started"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка запуска обработки документа: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start document processing: {str(e)}")


@router.delete("/namespaces/{namespace_id}/documents/{document_id}")
async def delete_document(
    namespace_id: str,
    document_id: str,
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep)
):
    """
    Удаляет документ из namespace.
    
    Args:
        namespace_id: ID namespace
        document_id: ID документа
        provider: Имя провайдера (опционально)
    
    Returns:
        Результат операции
    """
   
    
    try:
        status_repo = container.document_status_repository
        
        status = await status_repo.get_by_document_id(document_id)
        
        if status:
            s3_client = await container.get_s3_client()
            if s3_client and status.s3_key:
                try:
                    await s3_client.delete_file(status.s3_key)
                    logger.info(f"Удален файл из S3: {status.s3_key}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить файл из S3: {e}")
            
            await status_repo.delete_by_document_id(document_id)
        
        rag_provider = get_rag_provider(provider) if provider else container.rag_provider
        
        success = await rag_provider.delete_document(namespace_id, document_id)
        
        if not success and not status:
            raise HTTPException(status_code=404, detail="Document not found")
        
        logger.info(f"Удален документ: {document_id} из namespace {namespace_id}")
        
        return {"success": True, "document_id": document_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления документа: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: str,
    container: RAGContainer = Depends(get_container_dep)
):
    """
    Получает статус обработки документа.
    
    Args:
        document_id: ID документа
    
    Returns:
        Статус документа
    """
    try:
        status_repo = container.document_status_repository
        status = await status_repo.get_by_document_id(document_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Document status not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения статуса документа: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get document status: {str(e)}")


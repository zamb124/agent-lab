"""
Tasks для обслуживания и очистки ChromaDB.
"""

from typing import Dict, Any, List
from apps.chroma_worker.chroma_broker import broker
from core.rag.factory import get_default_rag_provider
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(queue_name="chroma")
async def cleanup_namespace_task(namespace_id: str) -> Dict[str, Any]:
    """
    Очистка namespace в ChromaDB.
    
    Удаляет все документы из указанного namespace.
    
    Args:
        namespace_id: ID namespace для очистки
        
    Returns:
        Результат очистки
    """
    logger.info(f"ChromaWorker: очистка namespace {namespace_id}")
    
    provider = get_default_rag_provider()
    
    # Получаем список всех документов
    try:
        documents = await provider.list_documents(namespace_id)
        document_ids = [doc.document_id for doc in documents]
        
        # Удаляем каждый документ
        deleted_count = 0
        for doc_id in document_ids:
            success = await provider.delete_document(namespace_id, doc_id)
            if success:
                deleted_count += 1
        
        logger.info(f"ChromaWorker: namespace {namespace_id} очищен, удалено {deleted_count} документов")
        
        return {
            "namespace": namespace_id,
            "status": "cleaned",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"ChromaWorker: ошибка очистки namespace {namespace_id}: {e}")
        return {
            "namespace": namespace_id,
            "status": "error",
            "error": str(e)
        }


@broker.task(queue_name="chroma")
async def list_documents_task(namespace_id: str) -> List[Dict[str, Any]]:
    """
    Получить список всех документов в namespace.
    
    Args:
        namespace_id: ID namespace
        
    Returns:
        Список документов с метаданными
    """
    logger.info(f"ChromaWorker: получение списка документов в namespace {namespace_id}")
    
    provider = get_default_rag_provider()
    documents = await provider.list_documents(namespace_id)
    
    return [
        {
            "document_id": doc.document_id,
            "document_name": doc.document_name,
            "namespace": doc.namespace,
            "metadata": doc.metadata
        }
        for doc in documents
    ]


@broker.task(queue_name="chroma", retry_on_error=True, max_retries=3)
async def reindex_document_task(
    namespace_id: str,
    document_id: str,
    s3_key: str,
    document_name: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Переиндексация документа (удаление + загрузка заново).
    
    Args:
        namespace_id: ID namespace
        document_id: ID документа для удаления
        s3_key: Ключ файла в S3
        document_name: Имя документа
        metadata: Новые метаданные
        
    Returns:
        Результат переиндексации
    """
    logger.info(f"ChromaWorker: переиндексация документа {document_id} в namespace {namespace_id}")
    
    provider = get_default_rag_provider()
    
    # Удаляем старый документ
    await provider.delete_document(namespace_id, document_id)
    
    # Загружаем заново
    document = await provider.upload_document_from_s3(
        namespace_id=namespace_id,
        s3_key=s3_key,
        document_name=document_name,
        metadata=metadata
    )
    
    logger.info(f"ChromaWorker: документ {document_name} переиндексирован, new_document_id={document.document_id}")
    
    return {
        "old_document_id": document_id,
        "new_document_id": document.document_id,
        "document_name": document.document_name,
        "namespace": namespace_id,
        "status": "reindexed"
    }


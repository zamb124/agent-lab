"""
Tasks для индексации документов в ChromaDB.
"""

from typing import Dict, Any
from apps.chroma_worker.chroma_broker import broker
from core.rag.factory import get_default_rag_provider
from core.logging import get_logger
from apps.rag.container import get_rag_container

logger = get_logger(__name__)


@broker.task(retry_on_error=True, max_retries=3, queue_name="chroma")
async def upload_document_task(
    namespace_id: str,
    s3_key: str,
    document_name: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Индексация документа в ChromaDB из S3.
    
    Args:
        namespace_id: ID namespace в ChromaDB
        s3_key: Ключ файла в S3
        document_name: Имя документа
        metadata: Метаданные документа
        
    Returns:
        Результат индексации с document_id
    """
    logger.info(f"ChromaWorker: индексация документа {document_name} в namespace {namespace_id}")
    
    container = get_rag_container()
    status_repo = container.document_status_repository
    
    try:
        provider = get_default_rag_provider()
        document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata
        )
        
        logger.info(f"ChromaWorker: документ {document_name} успешно проиндексирован, document_id={document.document_id}")
        
        await status_repo.update_status(
            document.document_id,
            "completed",
            s3_key=s3_key,
            s3_bucket=metadata.get("s3_bucket")
        )
        
        return {
            "document_id": document.document_id,
            "document_name": document_name,
            "namespace": namespace_id,
            "status": "completed"
        }
    except Exception as e:
        logger.error(f"ChromaWorker: ошибка индексации {document_name}: {e}")
        document_id = metadata.get("document_id")
        if document_id:
            await status_repo.update_status(document_id, "failed", error=str(e))
        raise


@broker.task(retry_on_error=True, max_retries=3, queue_name="chroma")
async def delete_document_task(namespace_id: str, document_id: str) -> Dict[str, Any]:
    """
    Удаление документа из ChromaDB.
    
    Args:
        namespace_id: ID namespace в ChromaDB
        document_id: ID документа для удаления
        
    Returns:
        Результат удаления
    """
    logger.info(f"ChromaWorker: удаление документа {document_id} из namespace {namespace_id}")
    
    provider = get_default_rag_provider()
    success = await provider.delete_document(namespace_id, document_id)
    
    if success:
        logger.info(f"ChromaWorker: документ {document_id} успешно удален")
    else:
        logger.warning(f"ChromaWorker: не удалось удалить документ {document_id}")
    
    return {
        "document_id": document_id,
        "namespace": namespace_id,
        "deleted": success
    }


@broker.task(retry_on_error=True, max_retries=3, queue_name="chroma")
async def process_document_upload(
    document_id: str,
    task_id: str,
    namespace_id: str,
    file_data: bytes,
    document_name: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Полная обработка загрузки документа:
    1. Загрузка в S3
    2. Парсинг
    3. Индексация в ChromaDB
    4. Обновление статуса в БД
    
    Args:
        document_id: ID документа
        task_id: ID задачи TaskIQ
        namespace_id: ID namespace в ChromaDB
        file_data: Сырые данные файла
        document_name: Имя файла
        metadata: Метаданные документа
        
    Returns:
        Результат обработки с document_id и статусом
    """
    logger.info(f"ChromaWorker: начало обработки документа {document_name} (doc_id={document_id}) [VERSION 2]")
    
    from core.config import get_settings
    settings = get_settings()
    status_repo = DocumentStatusRepository(settings.database.url)
    
    try:
        await status_repo.update_status(document_id, "processing")
        logger.info(f"ChromaWorker: статус изменен на processing для {document_id}")
        
        provider = get_default_rag_provider()
        
        s3_key, bucket = await provider._upload_bytes_to_s3(
            file_data, namespace_id, document_name
        )
        logger.info(f"ChromaWorker: файл загружен в S3: {s3_key}")
        
        document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata={**metadata, "document_id": document_id}
        )
        logger.info(f"ChromaWorker: документ проиндексирован: {document.document_id}")
        
        chunks_count = document.metadata.get("total_chunks")
        await status_repo.update_status(
            document_id,
            "completed",
            s3_key=s3_key,
            s3_bucket=bucket,
            chunks_count=chunks_count
        )
        logger.info(f"ChromaWorker: документ {document_id} успешно обработан")
        
        return {
            "document_id": document_id,
            "status": "completed",
            "s3_key": s3_key,
            "chunks_count": chunks_count
        }
        
    except Exception as e:
        logger.error(f"ChromaWorker: ошибка обработки документа {document_id}: {e}", exc_info=True)
        await status_repo.update_status(
            document_id,
            "failed",
            error=str(e)
        )
        raise


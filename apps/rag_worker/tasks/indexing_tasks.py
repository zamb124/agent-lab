"""
Tasks для индексации документов через pgvector.
"""

from typing import Any, Dict

from apps.rag.container import get_rag_container
from apps.rag_worker.broker import broker
from core.config import get_settings
from core.db.repositories.document_status_repository import DocumentStatusRepository
from core.logging import get_logger
from core.rag.factory import get_default_rag_provider
from core.rag.upload_profile_binding import UploadProfileBinding

logger = get_logger(__name__)


@broker.task(retry_on_error=True, max_retries=3, queue_name="rag")
async def index_rag_document_s3_task(
    company_id: str,
    namespace_id: str,
    s3_key: str,
    document_name: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Одна TaskIQ-задача: индексация S3-файла с конфигом ``rag.document_indexing`` (settings).
    """
    document_id = metadata.get("document_id")
    if not document_id:
        raise ValueError("metadata.document_id обязателен")

    container = get_rag_container()
    status_repo = container.document_status_repository

    settings = get_settings()
    binding = UploadProfileBinding(config=settings.rag.document_indexing)

    await status_repo.try_mark_processing(document_id)

    provider = get_default_rag_provider()
    meta = dict(metadata)

    try:
        document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=meta,
            upload_profile=binding,
        )
        chunks = int(document.metadata.get("total_chunks") or 0)
        runtime = document.metadata.get("indexing_runtime")
        await status_repo.record_indexing_done(
            document_id,
            chunks,
            indexing_runtime=runtime if isinstance(runtime, dict) else None,
        )
    except Exception as e:
        await status_repo.record_indexing_failed(document_id, str(e))
        raise

    logger.info(
        "RAG Worker: документ %s проиндексирован, document_id=%s",
        document_name,
        document.document_id,
    )

    return {
        "document_id": document.document_id,
        "document_name": document_name,
        "namespace": namespace_id,
        "status": "completed",
    }


@broker.task(retry_on_error=True, max_retries=3, queue_name="rag")
async def delete_document_task(namespace_id: str, document_id: str) -> Dict[str, Any]:
    """
    Удаление документа из vector_documents.

    Args:
        namespace_id: ID namespace
        document_id: ID документа для удаления

    Returns:
        Результат удаления
    """
    logger.info(f"RAG Worker: удаление документа {document_id} из namespace {namespace_id}")

    provider = get_default_rag_provider()
    success = await provider.delete_document(namespace_id, document_id)

    if success:
        logger.info(f"RAG Worker: документ {document_id} удален")
    else:
        logger.warning(f"RAG Worker: не удалось удалить документ {document_id}")

    return {
        "document_id": document_id,
        "namespace": namespace_id,
        "deleted": success,
    }


@broker.task(retry_on_error=True, max_retries=3, queue_name="rag")
async def process_document_upload(
    document_id: str,
    task_id: str,
    namespace_id: str,
    file_data: bytes,
    document_name: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Полная обработка загрузки документа:
    1. Загрузка в S3
    2. Одна задача индексации с ``rag.document_indexing``
    """
    logger.info(f"RAG Worker: обработка документа {document_name} (doc_id={document_id})")

    settings = get_settings()
    if not settings.database.rag_url:
        raise ValueError("database.rag_url не задан")
    status_repo = DocumentStatusRepository(settings.database.rag_url)

    company_id = metadata.get("company_id")
    if not company_id or not isinstance(company_id, str):
        raise ValueError("metadata.company_id обязателен (строка)")

    await status_repo.update_status(document_id, "processing")
    logger.info(f"RAG Worker: статус -> processing для {document_id}")

    provider = get_default_rag_provider()

    s3_key, bucket = await provider._upload_bytes_to_s3(file_data, namespace_id, document_name)
    logger.info(f"RAG Worker: файл загружен в S3: {s3_key}")

    merged_meta = {**metadata, "document_id": document_id, "s3_bucket": bucket}

    t = await index_rag_document_s3_task.kiq(
        company_id=company_id,
        namespace_id=namespace_id,
        s3_key=s3_key,
        document_name=document_name,
        metadata=dict(merged_meta),
    )

    await status_repo.finalize_enqueued_indexing_task(document_id, t.task_id)

    await status_repo.update_status(
        document_id,
        "processing",
        s3_key=s3_key,
        s3_bucket=bucket,
    )
    logger.info(
        "RAG Worker: документ %s: поставлена задача индексации task_id=%s",
        document_id,
        t.task_id,
    )

    return {
        "document_id": document_id,
        "status": "processing",
        "s3_key": s3_key,
        "task_id": t.task_id,
    }

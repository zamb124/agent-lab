"""
Tasks для индексации документов через pgvector.
"""

from typing import Dict, Any

from apps.rag_worker.broker import broker
from core.rag.factory import get_default_rag_provider
from core.logging import get_logger
from apps.rag.container import get_rag_container
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)


@broker.task(retry_on_error=True, max_retries=3, queue_name="rag")
async def upload_document_task(
    namespace_id: str,
    s3_key: str,
    document_name: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Индексация документа из S3.

    Args:
        namespace_id: ID namespace
        s3_key: Ключ файла в S3
        document_name: Имя документа
        metadata: Метаданные документа

    Returns:
        Результат индексации с document_id
    """
    logger.info(f"RAG Worker: индексация документа {document_name} в namespace {namespace_id}")

    container = get_rag_container()
    status_repo = container.document_status_repository

    trace_company_id = metadata.get("company_id")
    trace_user_id = metadata.get("uploaded_by_user_id")
    if not trace_company_id or str(trace_company_id).strip() == "":
        raise ValueError("metadata.company_id обязателен для rag.worker.index.upload_s3.")
    if not trace_user_id or str(trace_user_id).strip() == "":
        raise ValueError("metadata.uploaded_by_user_id обязателен для rag.worker.index.upload_s3.")

    async with traced_operation(
        "rag.worker.index.upload_s3",
        event_type="rag.ingest",
        operation_category="rag_ingest",
        resource_type="rag.namespace",
        resource_id=namespace_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: str(trace_company_id).strip(),
            trace_attributes.ATTR_USER_ID: str(trace_user_id).strip(),
            trace_attributes.ATTR_RAG_STAGE: "upload_from_s3",
            "platform.rag.document_name": document_name,
            "platform.rag.s3_key": s3_key,
        },
    ):
        provider = get_default_rag_provider()
        document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata,
        )

        logger.info(
            f"RAG Worker: документ {document_name} проиндексирован, document_id={document.document_id}"
        )

        await status_repo.update_status(
            document.document_id,
            "completed",
            s3_key=s3_key,
            s3_bucket=metadata.get("s3_bucket"),
        )

        return {
            "document_id": document.document_id,
            "document_name": document_name,
            "namespace": namespace_id,
            "status": "completed",
        }


@broker.task(retry_on_error=True, max_retries=3, queue_name="rag")
async def delete_document_task(
    namespace_id: str,
    document_id: str,
    company_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Удаление документа из vector_documents.

    Args:
        namespace_id: ID namespace
        document_id: ID документа для удаления

    Returns:
        Результат удаления
    """
    logger.info(f"RAG Worker: удаление документа {document_id} из namespace {namespace_id}")

    if company_id.strip() == "" or user_id.strip() == "":
        raise ValueError("company_id и user_id обязательны для rag.worker.index.delete.")

    async with traced_operation(
        "rag.worker.index.delete",
        event_type="rag.delete",
        operation_category="rag_ingest",
        resource_type="rag.document",
        resource_id=document_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id.strip(),
            trace_attributes.ATTR_USER_ID: user_id.strip(),
            "platform.rag.namespace_id": namespace_id,
        },
    ):
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
    2. Парсинг
    3. Индексация в vector_documents
    4. Обновление статуса в БД
    """
    logger.info(f"RAG Worker: обработка документа {document_name} (doc_id={document_id})")

    status_repo = get_rag_container().document_status_repository

    await status_repo.update_status(document_id, "processing")
    logger.info(f"RAG Worker: статус -> processing для {document_id}")

    trace_company_id = metadata.get("company_id")
    trace_user_id = metadata.get("uploaded_by_user_id")
    if not trace_company_id or str(trace_company_id).strip() == "":
        raise ValueError("metadata.company_id обязателен для rag.worker.ingest.full.")
    if not trace_user_id or str(trace_user_id).strip() == "":
        raise ValueError("metadata.uploaded_by_user_id обязателен для rag.worker.ingest.full.")

    async with traced_operation(
        "rag.worker.ingest.full",
        event_type="rag.ingest",
        operation_category="rag_ingest",
        resource_type="rag.document",
        resource_id=document_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: str(trace_company_id).strip(),
            trace_attributes.ATTR_USER_ID: str(trace_user_id).strip(),
            trace_attributes.ATTR_RAG_DOCUMENT_ID: document_id,
            trace_attributes.ATTR_RAG_STAGE: "upload_parse_index",
            "platform.rag.namespace_id": namespace_id,
            "platform.rag.file_bytes": len(file_data),
        },
    ):
        provider = get_default_rag_provider()

        s3_key, bucket = await provider._upload_bytes_to_s3(file_data, namespace_id, document_name)
        logger.info(f"RAG Worker: файл загружен в S3: {s3_key}")

        document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata={**metadata, "document_id": document_id},
        )
        logger.info(f"RAG Worker: документ проиндексирован: {document.document_id}")

        chunks_count = document.metadata.get("total_chunks")
        await status_repo.update_status(
            document_id,
            "completed",
            s3_key=s3_key,
            s3_bucket=bucket,
            chunks_count=chunks_count,
        )
        logger.info(f"RAG Worker: документ {document_id} обработан")

        return {
            "document_id": document_id,
            "status": "completed",
            "s3_key": s3_key,
            "chunks_count": chunks_count,
        }

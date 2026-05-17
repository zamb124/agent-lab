"""
Tasks для индексации документов через pgvector.
"""

from typing import Any, Dict

import core.tracing.attributes as trace_attributes
from apps.rag.container import get_rag_container
from apps.rag_worker.broker import broker
from core.config import get_settings
from core.context import Context, clear_context, set_context
from core.logging import get_logger
from core.models.identity_models import User
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)


async def _embedding_context_for_rag_worker(
    *,
    company_id: str,
    user_id: str,
    namespace_id: str,
) -> Context:
    """Загружает полную ``Company`` (вкл. ``metadata.ai_providers``) для воркера.

    Без этого per-company embedding override игнорировался бы в фоне (контекст ходит
    с пустым ``Company.metadata`` → резолвер не видит override).
    """
    cid = str(company_id).strip()
    uid = str(user_id).strip()
    ns = str(namespace_id).strip() or "default"
    if not cid:
        raise ValueError("company_id обязателен для контекста эмбеддингов в RAG worker")
    if not uid:
        raise ValueError("user_id обязателен для контекста эмбеддингов в RAG worker")

    container = get_rag_container()
    company = await container.company_repository.get(cid)
    if company is None:
        raise ValueError(f"RAG worker: компания {cid!r} не найдена")
    return Context(
        user=User(user_id=uid, name="RAG worker"),
        active_company=company,
        channel="rag_worker",
        active_namespace=ns,
    )


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

    meta_company = metadata.get("company_id")
    if not meta_company or str(meta_company).strip() != str(company_id).strip():
        raise ValueError("metadata.company_id должен совпадать с аргументом company_id задачи.")

    container = get_rag_container()
    status_repo = container.document_status_repository

    trace_company_id = metadata.get("company_id")
    trace_user_id = metadata.get("uploaded_by_user_id")
    if not trace_company_id or str(trace_company_id).strip() == "":
        raise ValueError("metadata.company_id обязателен для rag.worker.index.upload_s3.")
    if not trace_user_id or str(trace_user_id).strip() == "":
        raise ValueError("metadata.uploaded_by_user_id обязателен для rag.worker.index.upload_s3.")

    set_context(
        await _embedding_context_for_rag_worker(
            company_id=str(trace_company_id).strip(),
            user_id=str(trace_user_id).strip(),
            namespace_id=namespace_id,
        )
    )
    try:
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
            settings = get_settings()
            binding = UploadProfileBinding(config=settings.rag.document_indexing)

            await status_repo.try_mark_processing(document_id)

            provider = container.rag_provider
            meta = ensure_ttl_seconds_in_metadata(
                dict(metadata),
                default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
            )

            try:
                document = await provider.upload_document_from_s3(
                    namespace_id=namespace_id,
                    s3_key=s3_key,
                    document_name=document_name,
                    metadata=meta,
                    upload_profile=binding,
                )
            except Exception as e:
                await status_repo.record_indexing_failed(document_id, str(e))
                raise

            chunks = int(document.metadata.get("total_chunks") or 0)
            runtime = document.metadata.get("indexing_runtime")
            await status_repo.record_indexing_done(
                document_id,
                chunks,
                indexing_runtime=runtime if isinstance(runtime, dict) else None,
            )

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
    finally:
        clear_context()


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
    container = get_rag_container()

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
        provider = container.rag_provider
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

    container = get_rag_container()
    status_repo = container.document_status_repository

    company_id = metadata.get("company_id")
    if not company_id or not isinstance(company_id, str):
        raise ValueError("metadata.company_id обязателен (строка)")

    await status_repo.update_status(document_id, "processing")
    logger.info(f"RAG Worker: статус -> processing для {document_id}")

    trace_company_id = metadata.get("company_id")
    trace_user_id = metadata.get("uploaded_by_user_id")
    if not trace_company_id or str(trace_company_id).strip() == "":
        raise ValueError("metadata.company_id обязателен для rag.worker.ingest.full.")
    if not trace_user_id or str(trace_user_id).strip() == "":
        raise ValueError("metadata.uploaded_by_user_id обязателен для rag.worker.ingest.full.")

    set_context(
        await _embedding_context_for_rag_worker(
            company_id=str(trace_company_id).strip(),
            user_id=str(trace_user_id).strip(),
            namespace_id=namespace_id,
        )
    )
    try:
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
            provider = container.rag_provider

            s3_key, bucket = await provider._upload_bytes_to_s3(file_data, namespace_id, document_name)
            logger.info(f"RAG Worker: файл загружен в S3: {s3_key}")

            settings = get_settings()
            binding = UploadProfileBinding(config=settings.rag.document_indexing)
            upload_meta = ensure_ttl_seconds_in_metadata(
                {**metadata, "document_id": document_id},
                default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
            )

            document = await provider.upload_document_from_s3(
                namespace_id=namespace_id,
                s3_key=s3_key,
                document_name=document_name,
                metadata=upload_meta,
                upload_profile=binding,
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
    finally:
        clear_context()

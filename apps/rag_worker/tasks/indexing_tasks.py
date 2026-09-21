"""
Tasks для индексации документов через pgvector.
"""

import core.tracing.attributes as trace_attributes
from apps.rag.container import get_rag_container
from apps.rag.events import publish_rag_document_status_updated
from apps.rag_worker.tasks.task_names import (
    RAG_DELETE_DOCUMENT,
    RAG_INDEX_DOCUMENT_S3,
)
from core.config import get_settings
from core.context import Context, clear_context, set_context
from core.logging import get_logger
from core.models.identity_models import User
from core.rag.factory import get_rag_provider
from core.rag.indexable import (
    effective_rag_file_category,
    is_rag_indexable_file_category,
    rag_file_category_for_document_name,
)
from core.rag.models import RAGMetadata
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.tasks import platform_task
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, require_json_object

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
    ns = str(namespace_id).strip()
    if not cid:
        raise ValueError("company_id is required for the embeddings context in RAG worker")
    if not uid:
        raise ValueError("user_id is required for the embeddings context in RAG worker")
    if not ns:
        raise ValueError("namespace_id is required for the embeddings context in RAG worker")

    container = get_rag_container()
    company = await container.company_repository.get(cid)
    if company is None:
        raise ValueError(f"RAG worker: company {cid!r} not found")
    return Context(
        user=User(user_id=uid, name="RAG worker"),
        active_company=company,
        channel="rag_worker",
        active_namespace=ns,
    )


@platform_task(RAG_INDEX_DOCUMENT_S3)
async def index_rag_document_s3_task(
    company_id: str,
    namespace_id: str,
    s3_key: str,
    document_name: str,
    metadata: RAGMetadata,
    provider: str | None = None,
) -> JsonObject:
    """
    Одна TaskIQ-задача: индексация S3-файла с конфигом ``rag.document_indexing`` (settings).
    """
    document_id_value = metadata.get("document_id")
    if not isinstance(document_id_value, str) or not document_id_value.strip():
        raise ValueError("metadata.document_id is required")
    document_id = document_id_value.strip()

    meta_company = metadata.get("company_id")
    if not meta_company or str(meta_company).strip() != str(company_id).strip():
        raise ValueError("metadata.company_id must match the task company_id argument.")

    container = get_rag_container()
    status_repo = container.document_status_repository

    trace_company_id = metadata.get("company_id")
    trace_user_id = metadata.get("uploaded_by_user_id")
    if not trace_company_id or str(trace_company_id).strip() == "":
        raise ValueError("metadata.company_id is required for rag.worker.index.upload_s3.")
    if not trace_user_id or str(trace_user_id).strip() == "":
        raise ValueError("metadata.uploaded_by_user_id is required for rag.worker.index.upload_s3.")

    _ = set_context(
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
            await publish_rag_document_status_updated(
                company_id=str(trace_company_id).strip(),
                document_id=document_id,
                namespace_id=namespace_id,
                status="processing",
                document_name=document_name,
            )

            meta_file_category = metadata.get("file_category")
            if isinstance(meta_file_category, str) and meta_file_category.strip() != "":
                resolved_category = effective_rag_file_category(
                    file_category=meta_file_category,
                    document_name=document_name,
                )
            else:
                resolved_category = rag_file_category_for_document_name(document_name)

            if not is_rag_indexable_file_category(resolved_category):
                logger.info(
                    "rag.worker.skip.non.indexable",
                    document_id=document_id,
                    document_name=document_name,
                    file_category=resolved_category,
                )
                _ = await status_repo.record_indexing_done(document_id, 0)
                await publish_rag_document_status_updated(
                    company_id=str(trace_company_id).strip(),
                    document_id=document_id,
                    namespace_id=namespace_id,
                    status="completed",
                    document_name=document_name,
                    chunks_count=0,
                )
                return {
                    "document_id": document_id,
                    "document_name": document_name,
                    "namespace": namespace_id,
                    "status": "skipped",
                    "reason": "non_indexable_file_category",
                }

            rag_provider = (
                get_rag_provider(provider, settings=settings)
                if provider is not None
                else container.rag_provider
            )
            meta = ensure_ttl_seconds_in_metadata(
                dict(metadata),
                default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
            )

            try:
                document = await rag_provider.upload_document_from_s3(
                    namespace_id=namespace_id,
                    s3_key=s3_key,
                    document_name=document_name,
                    metadata=meta,
                    upload_profile=binding,
                )
            except Exception as e:
                await status_repo.record_indexing_failed(document_id, str(e))
                await publish_rag_document_status_updated(
                    company_id=str(trace_company_id).strip(),
                    document_id=document_id,
                    namespace_id=namespace_id,
                    status="failed",
                    document_name=document_name,
                    error_message=str(e),
                )
                raise

            raw_chunks = document.metadata.get("total_chunks")
            if not isinstance(raw_chunks, int) or isinstance(raw_chunks, bool):
                raise ValueError("RAG document metadata.total_chunks must be an integer")
            chunks = raw_chunks
            runtime = document.metadata.get("indexing_runtime")
            _ = await status_repo.record_indexing_done(
                document_id,
                chunks,
                indexing_runtime=(
                    require_json_object(runtime, "RAG document metadata.indexing_runtime")
                    if runtime is not None
                    else None
                ),
            )
            await publish_rag_document_status_updated(
                company_id=str(trace_company_id).strip(),
                document_id=document_id,
                namespace_id=namespace_id,
                status="completed",
                document_name=document_name,
                chunks_count=chunks,
            )

            logger.info("rag.worker.document_id", document_name=document_name, document_id=document.document_id)

            return {
                "document_id": document.document_id,
                "document_name": document_name,
                "namespace": namespace_id,
                "status": "completed",
            }
    finally:
        clear_context()


@platform_task(RAG_DELETE_DOCUMENT)
async def delete_document_task(
    namespace_id: str,
    document_id: str,
    company_id: str,
    user_id: str,
) -> JsonObject:
    """
    Удаление документа из vector_documents.

    Аргументы:
        namespace_id: ID namespace
        document_id: ID документа для удаления

    Возвращает:
        Результат удаления
    """
    logger.info("rag.worker.document_delete_started", document_id=document_id, namespace_id=namespace_id)
    container = get_rag_container()

    if company_id.strip() == "" or user_id.strip() == "":
        raise ValueError("company_id and user_id are required for rag.worker.index.delete.")

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
            logger.info("rag.worker.document_deleted", document_id=document_id)
        else:
            logger.warning("rag.worker.document_delete_failed", document_id=document_id)

        return {
            "document_id": document_id,
            "namespace": namespace_id,
            "deleted": success,
        }

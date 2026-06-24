"""
Tasks для индексации документов через pgvector.
"""

import core.tracing.attributes as trace_attributes
from apps.rag.container import get_rag_container
from apps.rag_worker.broker import broker
from core.config import get_settings
from core.context import Context, clear_context, set_context
from core.logging import get_logger
from core.models.identity_models import User
from core.rag.factory import get_rag_provider
from core.rag.models import RAGMetadata
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.tasks.kicker import kiq_task_name_with_context
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
        raise ValueError("company_id обязателен для контекста эмбеддингов в RAG worker")
    if not uid:
        raise ValueError("user_id обязателен для контекста эмбеддингов в RAG worker")
    if not ns:
        raise ValueError("namespace_id обязателен для контекста эмбеддингов в RAG worker")

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


RAG_INDEX_DOCUMENT_S3_TASK_NAME = "rag.index_document_s3"
RAG_INDEX_OFFICE_CATALOG_TASK_NAME = "rag.index_office_catalog"


@broker.task(
    task_name=RAG_INDEX_DOCUMENT_S3_TASK_NAME,
    retry_on_error=True,
    max_retries=3,
    queue_name="rag",
)
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
        raise ValueError("metadata.document_id обязателен")
    document_id = document_id_value.strip()

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
                raise

            raw_chunks = document.metadata.get("total_chunks")
            if not isinstance(raw_chunks, int) or isinstance(raw_chunks, bool):
                raise ValueError("RAG document metadata.total_chunks должен быть целым числом")
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


@broker.task(
    task_name=RAG_INDEX_OFFICE_CATALOG_TASK_NAME,
    retry_on_error=True,
    max_retries=3,
    queue_name="rag",
)
async def index_office_catalog_task(
    company_id: str,
    workspace_namespace: str,
    catalog_id: str,
    catalog_title: str,
    user_id: str,
    rag_namespace_id: str,
    items: list[JsonObject],
) -> JsonObject:
    """Batch enqueue index-file jobs for all bindings in an Office catalog."""
    if company_id.strip() == "":
        raise ValueError("company_id обязателен")
    if workspace_namespace.strip() == "":
        raise ValueError("workspace_namespace обязателен")
    if catalog_id.strip() == "":
        raise ValueError("catalog_id обязателен")
    if user_id.strip() == "":
        raise ValueError("user_id обязателен")
    if rag_namespace_id.strip() == "":
        raise ValueError("rag_namespace_id обязателен")

    container = get_rag_container()
    status_repo = container.document_status_repository
    enqueued_task_ids: list[str] = []

    for raw_item in items:
        item = require_json_object(raw_item, "office catalog index item")
        file_id_value = item.get("file_id")
        binding_id_value = item.get("binding_id")
        title_value = item.get("title")
        file_category_value = item.get("file_category")
        if not isinstance(file_id_value, str) or file_id_value.strip() == "":
            raise ValueError("items[].file_id обязателен")
        if not isinstance(binding_id_value, str) or binding_id_value.strip() == "":
            raise ValueError("items[].binding_id обязателен")
        if not isinstance(title_value, str) or title_value.strip() == "":
            raise ValueError("items[].title обязателен")
        if not isinstance(file_category_value, str) or file_category_value.strip() == "":
            raise ValueError("items[].file_category обязателен")

        file_id = file_id_value.strip()
        binding_id = binding_id_value.strip()
        file_record = await container.file_repository.get(file_id)
        if file_record is None:
            raise ValueError(f"FileRecord не найден: {file_id}")
        if file_record.company_id != company_id:
            raise ValueError(f"FileRecord {file_id} не принадлежит company_id={company_id}")

        metadata: RAGMetadata = {
            "source": "office",
            "company_id": company_id,
            "office_namespace": workspace_namespace.strip(),
            "catalog_id": catalog_id.strip(),
            "binding_id": binding_id,
            "document_title": title_value.strip(),
            "file_category": file_category_value.strip(),
            "uploaded_by_user_id": user_id.strip(),
            "ttl_seconds": 0,
            "external_file_owner": "peer",
            "document_id": file_id,
            "s3_bucket": file_record.s3_bucket,
        }
        settings = get_settings()
        metadata = ensure_ttl_seconds_in_metadata(
            metadata,
            default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
        )
        ttl_raw = metadata["ttl_seconds"]
        if not isinstance(ttl_raw, int) or isinstance(ttl_raw, bool):
            raise RuntimeError("ensure_ttl_seconds_in_metadata returned non-integer ttl_seconds")
        ttl_sec = ttl_raw

        document_name = file_record.original_name
        task_id_placeholder = f"pending_{file_id}"
        _ = await status_repo.create_status(
            document_id=file_id,
            task_id=task_id_placeholder,
            namespace_id=rag_namespace_id.strip(),
            document_name=document_name,
            file_size=file_record.file_size,
            ttl_seconds=ttl_sec,
            extra_metadata={},
        )
        task = await kiq_task_name_with_context(
            RAG_INDEX_DOCUMENT_S3_TASK_NAME,
            broker,
            company_id=company_id.strip(),
            namespace_id=rag_namespace_id.strip(),
            s3_key=file_record.s3_key,
            document_name=document_name,
            metadata=dict(metadata),
            provider=None,
        )
        _ = await status_repo.finalize_enqueued_indexing_task(file_id, task.task_id)
        enqueued_task_ids.append(task.task_id)

    logger.info(
        "Office catalog batch index enqueued catalog_id=%s rag_namespace_id=%s items=%s",
        catalog_id,
        rag_namespace_id,
        len(enqueued_task_ids),
    )
    return {
        "catalog_id": catalog_id.strip(),
        "catalog_title": catalog_title,
        "rag_namespace_id": rag_namespace_id.strip(),
        "enqueued_count": len(enqueued_task_ids),
        "task_ids": enqueued_task_ids,
    }


@broker.task(retry_on_error=True, max_retries=3, queue_name="rag")
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

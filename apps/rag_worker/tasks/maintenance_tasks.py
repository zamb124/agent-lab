"""
Tasks для обслуживания и очистки vector_documents.
"""

from datetime import datetime, timezone

from apps.rag_worker.di import Di
from apps.rag_worker.tasks.task_names import (
    RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK,
    RAG_CLEANUP_NAMESPACE,
    RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK,
    RAG_LIST_DOCUMENTS,
    RAG_REEMBED_STALE_DOCUMENTS_TICK,
    RAG_REINDEX_DOCUMENT,
)
from core.config import get_settings
from core.context import clear_context, set_context
from core.db.models.rag import DocumentProcessingStatus
from core.files.models import FileRecord
from core.logging import get_logger
from core.models.context_models import Context
from core.rag.models import (
    RAGCleanupExpiredDocumentsTickResult,
    RAGCleanupNamespaceTaskResult,
    RAGCleanupOrphanCompanyChunksTickResult,
    RAGListedDocumentTaskItem,
    RAGMetadata,
    RAGReembedTickResult,
    RAGReindexDocumentTaskResult,
)
from core.rag.reembed_stale_documents import execute_reembed_tick
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


@platform_task(RAG_CLEANUP_NAMESPACE)
async def cleanup_namespace_task(namespace_id: str, *, di: Di) -> RAGCleanupNamespaceTaskResult:
    """
    Очистка namespace -- удаление всех документов.

    Аргументы:
        namespace_id: ID namespace для очистки

    Возвращает:
        Результат очистки
    """
    logger.info("rag.worker.namespace_clear_started", namespace_id=namespace_id)

    provider = di.rag_provider

    success = await provider.delete_namespace(namespace_id)

    logger.info("rag.worker.namespace_cleared", namespace_id=namespace_id)

    return {
        "namespace": namespace_id,
        "status": "cleaned" if success else "empty",
    }


@platform_task(RAG_LIST_DOCUMENTS)
async def list_documents_task(namespace_id: str, *, di: Di) -> list[RAGListedDocumentTaskItem]:
    """
    Получить список всех документов в namespace.

    Аргументы:
        namespace_id: ID namespace

    Возвращает:
        Список документов с метаданными
    """
    logger.info("rag.worker.documents_list", namespace_id=namespace_id)

    provider = di.rag_provider
    documents = await provider.list_documents(namespace_id)

    return [
        {
            "document_id": doc.document_id,
            "document_name": doc.name,
            "namespace": doc.namespace,
            "metadata": doc.metadata,
        }
        for doc in documents
    ]


@platform_task(RAG_REINDEX_DOCUMENT)
async def reindex_document_task(
    context_data: JsonObject,
    namespace_id: str,
    document_id: str,
    s3_key: str,
    document_name: str,
    metadata: RAGMetadata,
    *,
    di: Di,
) -> RAGReindexDocumentTaskResult:
    """
    Переиндексация документа (удаление + загрузка заново).

    Аргументы:
        context_data: Сериализованный Context (``get_context().to_dict()`` на стороне постановки задачи)
        namespace_id: ID namespace
        document_id: ID документа для удаления
        s3_key: Ключ файла в S3
        document_name: Имя файла
        metadata: Метаданные

    Возвращает:
        Результат переиндексации
    """
    context = Context.from_dict(context_data)
    if not context.active_company:
        raise ValueError("context_data: active_company is required")
    _ = set_context(context)
    try:
        company_id = context.active_company.company_id

        logger.info(
            "rag.worker.namespace.company_id",
            document_id=document_id,
            namespace_id=namespace_id,
            company_id=company_id,
        )

        provider = di.rag_provider

        _ = await provider.delete_document(namespace_id, document_id)

        settings = get_settings()
        binding = UploadProfileBinding(config=settings.rag.document_indexing)
        base_meta = ensure_ttl_seconds_in_metadata(
            metadata,
            default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
        )
        last_document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=base_meta,
            upload_profile=binding,
        )
        logger.info(
            "rag.document.reindexed",
            document_name=document_name,
            document_id=last_document.document_id,
        )

        return {
            "old_document_id": document_id,
            "new_document_id": last_document.document_id,
            "document_name": last_document.name,
            "namespace": namespace_id,
            "status": "reindexed",
        }
    finally:
        clear_context()


@platform_task(RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK)
async def rag_cleanup_expired_documents_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> RAGCleanupExpiredDocumentsTickResult:
    """
    Удаляет просроченные по ``rag.ttl`` документы: shared FileRecord (если есть),
    строка ``document_processing_status``, вектора/внешний индекс через провайдер.

    ``company_id`` зарезервирован для будущей изоляции по тенанту; сейчас не применяется.
    """
    _ = company_id
    settings = get_settings()
    ttl_cfg = settings.rag.ttl
    if not ttl_cfg.cleanup_enabled:
        return {
            "skipped": True,
            "schedule_task_id": schedule_task_id,
            "candidates_total": 0,
            "deleted_documents": 0,
            "failed_documents": 0,
        }

    provider = di.rag_provider
    files_service = di.files_service
    now = datetime.now(timezone.utc)

    candidates = await DocumentProcessingStatus.list_expired_document_candidates(
        utc_now=now,
        limit=ttl_cfg.cleanup_batch_size,
    )

    deleted = 0
    failed = 0
    for namespace_id, document_id in candidates:
        try:
            file_record = await FileRecord.get(document_id)
            if file_record is not None:
                _ = await files_service.delete(document_id)
            _ = await DocumentProcessingStatus.delete_by_id(document_id)
            _ = await provider.delete_document(namespace_id, document_id)
            deleted += 1
        except Exception:
            logger.exception(
                "rag.cleanup_expired.document_failed",
                document_id=document_id,
                namespace_id=namespace_id,
            )
            failed += 1

    logger.info(
        "rag.cleanup_expired.tick_done",
        schedule_task_id=schedule_task_id,
        candidates=len(candidates),
        deleted_documents=deleted,
        failed_documents=failed,
    )

    return {
        "skipped": False,
        "schedule_task_id": schedule_task_id,
        "candidates_total": len(candidates),
        "deleted_documents": deleted,
        "failed_documents": failed,
    }


@platform_task(RAG_REEMBED_STALE_DOCUMENTS_TICK)
async def rag_reembed_stale_documents_tick(
    schedule_task_id: str,
    company_id: str | None = None,
) -> RAGReembedTickResult:
    _ = company_id
    return await execute_reembed_tick(
        channel="rag_worker",
        schedule_task_id=schedule_task_id,
    )


@platform_task(RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK)
async def rag_cleanup_orphan_company_chunks_tick(
    schedule_task_id: str,
    company_id: str | None = None,
    *,
    di: Di,
) -> RAGCleanupOrphanCompanyChunksTickResult:
    """
    Батчево удаляет ``vector_documents`` без ``company_id`` (NULL/'').

    Такие строки осиротевшие: биллинг и поиск по тенанту невозможны.
    Cleanup-тик удаляет их, reembed-тик их не обрабатывает.
    """
    _ = company_id
    if not schedule_task_id or not schedule_task_id.strip():
        raise ValueError("rag_cleanup_orphan_company_chunks_tick: schedule_task_id is required")
    settings = get_settings()
    cfg = settings.rag.ttl
    if not cfg.orphan_cleanup_enabled:
        return {
            "skipped": True,
            "schedule_task_id": schedule_task_id,
            "deleted": 0,
        }
    provider = di.rag_provider
    deleted = await provider.delete_orphan_company_chunks(limit=cfg.orphan_cleanup_batch_size)
    logger.info(
        "rag.orphan_cleanup.tick_done",
        schedule_task_id=schedule_task_id,
        batch_size=cfg.orphan_cleanup_batch_size,
        deleted=deleted,
    )
    return {
        "skipped": False,
        "schedule_task_id": schedule_task_id,
        "batch_size": cfg.orphan_cleanup_batch_size,
        "deleted": deleted,
    }

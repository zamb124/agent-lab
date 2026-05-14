"""
Tasks для обслуживания и очистки vector_documents.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from apps.rag.container import get_rag_container
from apps.rag_worker.broker import broker
from core.config import get_settings
from core.context import Context, clear_context, set_context
from core.files.processors import FileProcessor
from core.logging import get_logger
from core.rag.reembed_stale_documents import execute_reembed_tick
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding

logger = get_logger(__name__)


@broker.task(queue_name="rag")
async def cleanup_namespace_task(namespace_id: str) -> Dict[str, Any]:
    """
    Очистка namespace -- удаление всех документов.

    Args:
        namespace_id: ID namespace для очистки

    Returns:
        Результат очистки
    """
    logger.info(f"RAG Worker: очистка namespace {namespace_id}")

    provider = get_rag_container().rag_provider

    success = await provider.delete_namespace(namespace_id)

    logger.info(f"RAG Worker: namespace {namespace_id} очищен")

    return {
        "namespace": namespace_id,
        "status": "cleaned" if success else "empty",
    }


@broker.task(queue_name="rag")
async def list_documents_task(namespace_id: str) -> List[Dict[str, Any]]:
    """
    Получить список всех документов в namespace.

    Args:
        namespace_id: ID namespace

    Returns:
        Список документов с метаданными
    """
    logger.info(f"RAG Worker: получение списка документов в namespace {namespace_id}")

    provider = get_rag_container().rag_provider
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


@broker.task(queue_name="rag", retry_on_error=True, max_retries=3)
async def reindex_document_task(
    context_data: Dict[str, Any],
    namespace_id: str,
    document_id: str,
    s3_key: str,
    document_name: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Переиндексация документа (удаление + загрузка заново).

    Args:
        context_data: Сериализованный Context (``get_context().to_dict()`` на стороне постановки задачи)
        namespace_id: ID namespace
        document_id: ID документа для удаления
        s3_key: Ключ файла в S3
        document_name: Имя файла
        metadata: Метаданные

    Returns:
        Результат переиндексации
    """
    context = Context.from_dict(context_data)
    if not context.active_company:
        raise ValueError("context_data: active_company обязателен")
    set_context(context)
    try:
        company_id = context.active_company.company_id

        logger.info(
            "RAG Worker: переиндексация документа %s в namespace %s (company_id=%s)",
            document_id,
            namespace_id,
            company_id,
        )

        provider = get_rag_container().rag_provider

        await provider.delete_document(namespace_id, document_id)

        settings = get_settings()
        binding = UploadProfileBinding(config=settings.rag.document_indexing)
        base_meta = ensure_ttl_seconds_in_metadata(
            dict(metadata),
            default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
        )
        last_document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=dict(base_meta),
            upload_profile=binding,
        )
        logger.info(
            f"RAG Worker: документ {document_name} переиндексирован, document_id={last_document.document_id}"
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


@broker.task(
    task_name="rag_cleanup_expired_documents_tick",
    queue_name="rag",
    retry_on_error=True,
    max_retries=2,
)
async def rag_cleanup_expired_documents_tick(
    scheduler_task_id: str | None = None,
    company_id: str | None = None,
) -> Dict[str, Any]:
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
            "scheduler_task_id": scheduler_task_id,
            "candidates_total": 0,
            "deleted_documents": 0,
            "failed_documents": 0,
        }

    container = get_rag_container()
    status_repo = container.document_status_repository
    provider = container.rag_provider
    processor = FileProcessor(file_repository=container.file_repository)
    now = datetime.now(timezone.utc)

    candidates = await status_repo.list_expired_document_candidates(
        utc_now=now,
        limit=ttl_cfg.cleanup_batch_size,
    )

    deleted = 0
    failed = 0
    for namespace_id, document_id in candidates:
        try:
            file_record = await container.file_repository.get(document_id)
            if file_record is not None:
                await processor.delete_file(document_id)
            await status_repo.delete_by_document_id(document_id)
            await provider.delete_document(namespace_id, document_id)
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
        scheduler_task_id=scheduler_task_id,
        candidates=len(candidates),
        deleted_documents=deleted,
        failed_documents=failed,
    )

    return {
        "skipped": False,
        "scheduler_task_id": scheduler_task_id,
        "candidates_total": len(candidates),
        "deleted_documents": deleted,
        "failed_documents": failed,
    }


@broker.task(
    task_name="rag_reembed_stale_documents_tick",
    queue_name="rag",
    retry_on_error=True,
    max_retries=2,
)
async def rag_reembed_stale_documents_tick(
    scheduler_task_id: str,
    company_id: str | None = None,
) -> Dict[str, Any]:
    _ = company_id
    return await execute_reembed_tick(
        container=get_rag_container(),
        channel="rag_worker",
        scheduler_task_id=scheduler_task_id,
    )


@broker.task(
    task_name="rag_cleanup_orphan_company_chunks_tick",
    queue_name="rag",
    retry_on_error=True,
    max_retries=2,
)
async def rag_cleanup_orphan_company_chunks_tick(
    scheduler_task_id: str,
    company_id: str | None = None,
) -> Dict[str, Any]:
    """
    Батчево удаляет ``vector_documents`` без ``company_id`` (NULL/'').

    Такие строки осиротевшие — биллинг и поиск по тенанту невозможны; они появляются
    исторически (legacy) и подлежат удалению. reembed-тик их не обрабатывает.
    """
    _ = company_id
    if not scheduler_task_id or not scheduler_task_id.strip():
        raise ValueError("rag_cleanup_orphan_company_chunks_tick: scheduler_task_id обязателен")
    settings = get_settings()
    cfg = settings.rag.ttl
    if not cfg.orphan_cleanup_enabled:
        return {
            "skipped": True,
            "scheduler_task_id": scheduler_task_id,
            "deleted": 0,
        }
    provider = get_rag_container().rag_provider
    deleted = await provider.delete_orphan_company_chunks(limit=cfg.orphan_cleanup_batch_size)
    logger.info(
        "rag.orphan_cleanup.tick_done",
        scheduler_task_id=scheduler_task_id,
        batch_size=cfg.orphan_cleanup_batch_size,
        deleted=deleted,
    )
    return {
        "skipped": False,
        "scheduler_task_id": scheduler_task_id,
        "batch_size": cfg.orphan_cleanup_batch_size,
        "deleted": deleted,
    }

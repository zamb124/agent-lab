"""
Перевекторизация устаревших чанков CRM vector_documents с ``embedding_model IS NULL``.

Использует стандартную фабрику RAG-провайдеров (которая учитывает per-company embedding override).
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

from apps.crm.container import get_crm_container
from apps.crm_worker.broker import broker
from core.config import get_settings
from core.context import clear_context, set_context
from core.context.system_task_context import build_system_auth_context
from core.logging import get_logger
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider

logger = get_logger(__name__)


@runtime_checkable
class _CrmStaleReembedProvider(Protocol):
    def _embedding_model_name(self) -> str: ...

    async def reembed_stale_documents(self, *, batch_size: int, target_embedding_model: str) -> int: ...


@broker.task(
    task_name="crm_reembed_stale_documents_tick",
    queue_name="crm",
    retry_on_error=True,
    max_retries=2,
)
async def crm_reembed_stale_documents_tick(
    scheduler_task_id: str | None = None,
    company_id: str | None = None,
) -> Dict[str, Any]:
    """
    Перевекторизует чанки CRM с ``embedding_model IS NULL``.

    Один тик обрабатывает не более ``rag.ttl.reembed_batch_size`` чанков.
    Отключение: ``rag.ttl.reembed_enabled: false``.
    """
    _ = company_id
    settings = get_settings()
    reembed_cfg = settings.rag.ttl
    if not reembed_cfg.reembed_enabled:
        return {
            "skipped": True,
            "scheduler_task_id": scheduler_task_id,
            "reembedded": 0,
        }

    system_context = await build_system_auth_context(
        container=get_crm_container(),
        trace_id=f"scheduler:crm_reembed_stale_documents:{scheduler_task_id or 'manual'}",
        session_id=f"crm_reembed_stale_documents:{scheduler_task_id or 'manual'}",
        channel="crm_worker",
    )
    set_context(system_context)
    try:
        provider = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)
        if not isinstance(provider, _CrmStaleReembedProvider):
            raise RuntimeError(
                "crm_reembed_stale_documents: провайдер должен поддерживать "
                f"_embedding_model_name и reembed_stale_documents; получено {type(provider).__name__}"
            )
        target_model = provider._embedding_model_name()
        batch_size = reembed_cfg.reembed_batch_size
        reembedded = await provider.reembed_stale_documents(
            batch_size=batch_size,
            target_embedding_model=target_model,
        )
    finally:
        clear_context()

    logger.info(
        "crm.reembed_stale.tick_done",
        scheduler_task_id=scheduler_task_id,
        target_embedding_model=target_model,
        batch_size=batch_size,
        reembedded=reembedded,
    )

    return {
        "skipped": False,
        "scheduler_task_id": scheduler_task_id,
        "target_embedding_model": target_model,
        "batch_size": batch_size,
        "reembedded": reembedded,
    }

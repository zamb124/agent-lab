"""TaskIQ: refresh OpenRouter free model candidate cache."""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from apps.idle_worker.broker import broker as idle_broker
from core.clients.llm.openrouter_free_models import refresh_openrouter_free_models_cache
from core.logging import get_logger

logger = get_logger(__name__)


@idle_broker.task(task_name="refresh_openrouter_free_models_task", queue_name="idle")
async def refresh_openrouter_free_models_task(
    scheduler_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
) -> dict[str, object]:
    del company_id, system_task
    container = get_container()
    result = await refresh_openrouter_free_models_cache(
        container.redis_client,
        get_settings(),
    )
    logger.info(
        "openrouter.free_models.refresh_task_done",
        scheduler_task_id=scheduler_task_id,
        count=result.get("count"),
    )
    return result

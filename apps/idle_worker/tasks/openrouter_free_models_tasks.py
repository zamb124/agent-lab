"""TaskIQ: refresh OpenRouter free model candidate cache."""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from core.clients.llm.openrouter_free_models import refresh_openrouter_free_models_cache
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


@idle_broker.task(task_name="refresh_openrouter_free_models_task", queue_name="idle")
async def refresh_openrouter_free_models_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
) -> JsonObject:
    del company_id, system_task
    container = get_container()
    result = await refresh_openrouter_free_models_cache(
        container.redis_client,
        get_settings(),
    )
    logger.info(
        "openrouter.free_models.refresh_task_done",
        schedule_task_id=schedule_task_id,
        count=result.get("count"),
    )
    return result

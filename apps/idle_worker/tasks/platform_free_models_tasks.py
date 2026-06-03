"""TaskIQ: refresh provider-neutral platform free model candidate cache."""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from core.ai.free_pool import refresh_platform_free_models_cache
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


@idle_broker.task(task_name="refresh_platform_free_models_task", queue_name="idle")
async def refresh_platform_free_models_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
) -> JsonObject:
    del company_id, system_task
    container = get_container()
    result = await refresh_platform_free_models_cache(
        container.redis_client,
        get_settings(),
        container.ai_model_catalog_repository,
        model_score_provider=container.llm_model_score_repository,
    )
    logger.info(
        "platform_free_models.refresh_task_done",
        schedule_task_id=schedule_task_id,
        count=result.get("count"),
        providers=result.get("providers"),
    )
    return result

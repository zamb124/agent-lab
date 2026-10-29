"""TaskIQ: refresh provider-neutral platform free model candidate cache."""

from __future__ import annotations

from apps.idle.di import Di
from core.ai.free_pool import refresh_platform_free_models_cache
from core.ai.task_names import TASK_REFRESH_PLATFORM_FREE_MODELS
from core.config import get_settings
from core.logging import get_logger
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


@platform_task(TASK_REFRESH_PLATFORM_FREE_MODELS)
async def refresh_platform_free_models_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    del company_id, system_task
    result = await refresh_platform_free_models_cache(
        di.redis_client,
        get_settings(),
    )
    logger.info(
        "platform_free_models.refresh_task_done",
        schedule_task_id=schedule_task_id,
        count=result.get("count"),
        providers=result.get("providers"),
    )
    return result

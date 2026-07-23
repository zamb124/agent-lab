"""Idle task: LLM-описания tag-групп platform tools."""

from __future__ import annotations

from apps.idle_worker.container import get_container
from apps.idle_worker.tasks.llm_models_tasks import build_scheduler_auth_context
from apps.idle_worker.tasks.task_names import TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK
from core.context import clear_context, set_context
from core.logging import get_logger
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


@platform_task(TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK)
async def tool_tag_groups_describe_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
) -> JsonObject:
    """Обновляет платформенные LLM-описания tag-групп tools."""
    _ = company_id
    _ = system_task
    container = get_container()
    scheduler_context = await build_scheduler_auth_context(
        container=container,
        trace_id=f"scheduler:tool_tag_groups_describe:{schedule_task_id}",
        session_id=f"tool_tag_groups_describe:{schedule_task_id}",
    )
    set_context(scheduler_context)
    try:
        stats = await container.tool_tag_group_service.describe_all_platform_tags()
        logger.info(
            "tool_tag_groups.describe_tick_done",
            schedule_task_id=schedule_task_id,
            tags_total=stats.tags_total,
            tags_updated=stats.tags_updated,
            tags_skipped=stats.tags_skipped,
        )
        return stats.model_dump(mode="json")
    finally:
        clear_context()

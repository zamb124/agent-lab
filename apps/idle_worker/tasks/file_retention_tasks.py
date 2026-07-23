"""File retention purge and backfill ticks (idle queue)."""

from __future__ import annotations

from apps.idle_worker.container import get_container
from apps.idle_worker.tasks.task_names import (
    TASK_FILE_RETENTION_BACKFILL_TICK,
    TASK_FILE_RETENTION_PURGE_TICK,
)
from core.config import get_settings
from core.files.backfill import FileRetentionBackfillService
from core.logging import get_logger
from core.tasks import platform_task

logger = get_logger(__name__)


@platform_task(TASK_FILE_RETENTION_PURGE_TICK)
async def file_retention_purge_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int | list[str]]:
    settings = get_settings()
    if not settings.files.retention.purge_enabled:
        return {"purged_count": 0, "failed_count": 0}

    container = get_container()
    result = await container.file_purge_service.purge_expired_batch()
    logger.info(
        "file_retention_purge_tick done: purged=%s failed=%s schedule_task_id=%s company_id=%s",
        result.purged_count,
        len(result.failed_file_ids),
        schedule_task_id,
        company_id,
    )
    return {
        "purged_count": result.purged_count,
        "failed_count": len(result.failed_file_ids),
    }


@platform_task(TASK_FILE_RETENTION_BACKFILL_TICK)
async def file_retention_backfill_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    settings = get_settings()
    batch_limit = settings.files.retention.backfill_batch_size
    container = get_container()
    backfill = FileRetentionBackfillService(file_repository=container.file_repository)
    result = await backfill.backfill_batch(limit=batch_limit)
    logger.info(
        "file_retention_backfill_tick done: scanned=%s updated=%s skipped=%s schedule_task_id=%s company_id=%s",
        result.scanned,
        result.updated,
        result.skipped,
        schedule_task_id,
        company_id,
    )
    return {
        "scanned": result.scanned,
        "updated": result.updated,
        "skipped": result.skipped,
    }

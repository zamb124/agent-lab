"""File retention purge and backfill ticks (idle queue)."""

from __future__ import annotations

from apps.idle.di import Di
from apps.idle.tasks.task_names import (
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
    *,
    di: Di,
) -> dict[str, int | list[str]]:
    settings = get_settings()
    if not settings.files.retention.purge_enabled:
        return {"purged_count": 0, "failed_count": 0}

    result = await di.file_purge_service.purge_expired_batch()
    logger.info(
        "idle.file_retention_purge_tick",
        purged=result.purged_count,
        failed=len(result.failed_file_ids),
        schedule_task_id=schedule_task_id,
        company_id=company_id,
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
    backfill = FileRetentionBackfillService()
    result = await backfill.backfill_batch(limit=batch_limit)
    logger.info(
        "idle.file_retention_backfill_tick",
        scanned=result.scanned,
        updated=result.updated,
        skipped=result.skipped,
        schedule_task_id=schedule_task_id,
        company_id=company_id,
    )
    return {
        "scanned": result.scanned,
        "updated": result.updated,
        "skipped": result.skipped,
    }

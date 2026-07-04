"""GC orphan platform_schedules keys in TaskIQ broker Redis."""

from __future__ import annotations

from apps.idle_worker.broker import broker as idle_broker
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.logging import get_logger
from core.scheduler.platform_schedules_gc import PlatformSchedulesGcService
from core.scheduler.repository import SchedulerTaskRepository

logger = get_logger(__name__)

PLATFORM_SCHEDULES_GC_TASK_NAME = "platform_schedules_gc_tick"


@idle_broker.task(task_name=PLATFORM_SCHEDULES_GC_TASK_NAME, queue_name="idle")
async def platform_schedules_gc_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int | list[str]]:
    _ = schedule_task_id, company_id
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required for platform_schedules_gc_tick")

    broker_redis = RedisClient(settings.tasks.broker_url)
    await broker_redis.connect()
    try:
        gc_service = PlatformSchedulesGcService(
            broker_redis_client=broker_redis,
            scheduler_task_repository=SchedulerTaskRepository(
                db_url=settings.database.shared_url,
            ),
        )
        result = await gc_service.run_gc(dry_run=False)
    finally:
        await broker_redis.close()

    logger.info(
        "platform_schedules_gc_tick done: scanned=%s deleted=%s",
        result.scanned_keys,
        result.deleted_orphans,
    )
    return {
        "scanned_keys": result.scanned_keys,
        "deleted_orphans": result.deleted_orphans,
        "orphan_samples": list(result.orphan_samples),
    }

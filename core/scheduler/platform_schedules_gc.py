"""GC orphan ключей platform_schedules в TaskIQ broker Redis."""

from __future__ import annotations

from dataclasses import dataclass

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.scheduler.repository import SchedulerTaskRepository

logger = get_logger(__name__)

PLATFORM_SCHEDULES_DATA_PREFIX = "platform_schedules:data:"


@dataclass(frozen=True, slots=True)
class PlatformSchedulesGcResult:
    scanned_keys: int
    deleted_orphans: int
    orphan_samples: tuple[str, ...]


class PlatformSchedulesGcService:
    """Удаляет Redis-ключи platform_schedules без записи в scheduler_tasks."""

    def __init__(
        self,
        *,
        broker_redis_client: RedisClient,
        scheduler_task_repository: SchedulerTaskRepository,
    ) -> None:
        self._broker_redis: RedisClient = broker_redis_client
        self._scheduler_task_repository: SchedulerTaskRepository = scheduler_task_repository

    @staticmethod
    def _schedule_id_from_key(redis_key: str) -> str | None:
        if not redis_key.startswith(PLATFORM_SCHEDULES_DATA_PREFIX):
            return None
        schedule_id = redis_key.removeprefix(PLATFORM_SCHEDULES_DATA_PREFIX)
        if schedule_id.strip() == "":
            return None
        return schedule_id

    async def run_gc(self, *, dry_run: bool = False) -> PlatformSchedulesGcResult:
        known_schedule_ids = await self._scheduler_task_repository.list_all_schedule_ids()
        redis_keys = await self._broker_redis.scan_keys(f"{PLATFORM_SCHEDULES_DATA_PREFIX}*")
        orphan_keys: list[str] = []
        for redis_key in redis_keys:
            schedule_id = self._schedule_id_from_key(redis_key)
            if schedule_id is None:
                continue
            if schedule_id not in known_schedule_ids:
                orphan_keys.append(redis_key)

        deleted = 0
        if not dry_run and orphan_keys:
            deleted = await self._broker_redis.delete(*orphan_keys)

        samples = tuple(orphan_keys[:10])
        logger.info(
            "platform_schedules.gc_completed",
            scanned_keys=len(redis_keys),
            deleted_orphans=deleted,
            dry_run=dry_run,
        )
        return PlatformSchedulesGcResult(
            scanned_keys=len(redis_keys),
            deleted_orphans=deleted,
            orphan_samples=samples,
        )

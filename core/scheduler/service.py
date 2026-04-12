"""Сервис платформенного scheduler."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter
from taskiq.kicker import AsyncKicker

from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduledTask,
    PlatformScheduleCreateRequest,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.scheduler.repository import SchedulerTaskRepository
from core.scheduler.source import get_schedule_source


class SchedulerService:
    """Бизнес-логика scheduler control-plane."""

    def __init__(
        self,
        repository: SchedulerTaskRepository,
        redis_url: str,
        broker_for_queue: Callable[[str], Any],
    ) -> None:
        self._repository = repository
        self._redis_url = redis_url
        self._broker_for_queue = broker_for_queue

    @staticmethod
    def _status_value(status: ScheduledTaskStatus | str) -> str:
        return status.value if hasattr(status, "value") else str(status)

    def _calculate_next_run_at(
        self,
        task: PlatformScheduledTask,
        *,
        base_time_utc: datetime | None = None,
    ) -> datetime | None:
        now_utc = base_time_utc or datetime.now(timezone.utc)
        if task.schedule_type == PlatformScheduleType.ONE_TIME:
            return task.run_at
        if task.schedule_type == PlatformScheduleType.INTERVAL:
            if task.interval_seconds is None:
                raise ValueError("interval_seconds is required for schedule_type=interval")
            return now_utc + timedelta(seconds=task.interval_seconds)
        if task.schedule_type == PlatformScheduleType.CRON:
            if not task.cron:
                raise ValueError("cron is required for schedule_type=cron")
            now_in_task_tz = now_utc.astimezone(ZoneInfo(task.timezone))
            return croniter(task.cron, now_in_task_tz).get_next(datetime).astimezone(timezone.utc)
        raise ValueError(f"unsupported schedule_type: {task.schedule_type}")

    def _enrich_next_run_at(self, task: PlatformScheduledTask) -> PlatformScheduledTask:
        if task.status != ScheduledTaskStatus.PENDING:
            return task
        if task.next_run_at is not None:
            return task
        if task.schedule_type not in (PlatformScheduleType.CRON, PlatformScheduleType.INTERVAL):
            return task
        task.next_run_at = self._calculate_next_run_at(task)
        return task

    @staticmethod
    def _interval_seconds_from_taskiq(interval: Any) -> int | None:
        if interval is None:
            return None
        if isinstance(interval, timedelta):
            return int(interval.total_seconds())
        if isinstance(interval, int):
            return interval
        raise ValueError(f"unsupported interval type from redis schedule: {type(interval)}")

    @staticmethod
    def _build_task_labels(task: PlatformScheduledTask) -> dict[str, str]:
        if not task.queue_name:
            raise ValueError(f"queue_name is required for scheduled task: {task.task_name}")
        return {"queue_name": task.queue_name}

    async def _create_schedule(self, task: PlatformScheduledTask) -> str:
        source = get_schedule_source(self._redis_url)
        await source.startup()
        broker = self._broker_for_queue(task.queue_name)
        kicker = AsyncKicker(
            task_name=task.task_name,
            broker=broker,
            labels=self._build_task_labels(task),
        )

        if task.schedule_type == PlatformScheduleType.CRON:
            if not task.cron:
                raise ValueError("cron is required for schedule_type=cron")
            schedule = await kicker.schedule_by_cron(source, task.cron, **task.payload)
            return schedule.schedule_id

        if task.schedule_type == PlatformScheduleType.INTERVAL:
            if task.interval_seconds is None:
                raise ValueError("interval_seconds is required for schedule_type=interval")
            schedule = await kicker.schedule_by_interval(
                source,
                timedelta(seconds=task.interval_seconds),
                **task.payload,
            )
            return schedule.schedule_id

        if task.run_at is None:
            raise ValueError("run_at is required for schedule_type=one_time")
        schedule = await kicker.schedule_by_time(source, task.run_at, **task.payload)
        return schedule.schedule_id

    async def create(
        self,
        company_id: str,
        user_id: str | None,
        request: PlatformScheduleCreateRequest,
    ) -> PlatformScheduledTask:
        now = datetime.now(timezone.utc)
        task = PlatformScheduledTask(
            id=str(uuid4()),
            company_id=company_id,
            target_service=request.target_service,
            task_name=request.task_name,
            queue_name=request.queue_name,
            schedule_type=request.schedule_type,
            cron=request.cron,
            interval_seconds=request.interval_seconds,
            run_at=request.run_at,
            timezone=request.timezone,
            payload=request.payload,
            status=ScheduledTaskStatus.PENDING,
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
            next_run_at=None,
        )
        task.payload["scheduler_task_id"] = task.id
        task.payload["company_id"] = company_id
        task.next_run_at = self._calculate_next_run_at(task, base_time_utc=now)
        task.schedule_id = await self._create_schedule(task)
        return await self._repository.save(task)

    async def get(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self._repository.get(company_id=company_id, schedule_task_id=schedule_task_id)
        if task is None:
            raise ValueError(f"schedule task not found: {schedule_task_id}")
        return self._enrich_next_run_at(task)

    async def get_redis_snapshot(self, company_id: str, schedule_task_id: str) -> PlatformRedisScheduleSnapshot:
        task = await self.get(company_id=company_id, schedule_task_id=schedule_task_id)
        if task.schedule_id is None:
            return PlatformRedisScheduleSnapshot(
                schedule_task_id=task.id,
                company_id=task.company_id,
                schedule_id=None,
                exists_in_redis=False,
                status=task.status,
                task_name=task.task_name,
                missing_reason="schedule_id is null",
            )

        source = get_schedule_source(self._redis_url)
        await source.startup()
        schedules = await source.get_schedules()
        matched = [item for item in schedules if item.schedule_id == task.schedule_id]
        if len(matched) == 0:
            return PlatformRedisScheduleSnapshot(
                schedule_task_id=task.id,
                company_id=task.company_id,
                schedule_id=task.schedule_id,
                exists_in_redis=False,
                status=task.status,
                task_name=task.task_name,
                missing_reason="schedule_id not found in redis source",
            )
        if len(matched) > 1:
            raise ValueError(f"duplicate schedule_id in redis source: {task.schedule_id}")

        redis_schedule = matched[0]
        return PlatformRedisScheduleSnapshot(
            schedule_task_id=task.id,
            company_id=task.company_id,
            schedule_id=task.schedule_id,
            exists_in_redis=True,
            status=task.status,
            task_name=redis_schedule.task_name,
            cron=redis_schedule.cron,
            interval_seconds=self._interval_seconds_from_taskiq(redis_schedule.interval),
            run_at=redis_schedule.time,
            taskiq_task_id=redis_schedule.task_id,
            kwargs=redis_schedule.kwargs,
            labels=redis_schedule.labels,
            missing_reason=None,
        )

    async def list(self, company_id: str, filters: PlatformScheduleFilter) -> list[PlatformScheduledTask]:
        tasks = await self._repository.list(company_id=company_id, filters=filters)
        return [self._enrich_next_run_at(task) for task in tasks]

    async def count(self, company_id: str, filters: PlatformScheduleFilter) -> int:
        return await self._repository.count(company_id=company_id, filters=filters)

    async def pause(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self.get(company_id, schedule_task_id)
        if task.status != ScheduledTaskStatus.PENDING:
            raise ValueError(f"task status must be pending, got {self._status_value(task.status)}")
        if not task.schedule_id:
            raise ValueError(f"schedule_id is required for task {schedule_task_id}")
        source = get_schedule_source(self._redis_url)
        await source.startup()
        await source.delete_schedule(task.schedule_id)
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=ScheduledTaskStatus.PAUSED,
            schedule_id=None,
        )
        return await self.get(company_id, schedule_task_id)

    async def resume(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self.get(company_id, schedule_task_id)
        if task.status != ScheduledTaskStatus.PAUSED:
            raise ValueError(f"task status must be paused, got {self._status_value(task.status)}")
        schedule_id = await self._create_schedule(task)
        next_run_at = self._calculate_next_run_at(task)
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=ScheduledTaskStatus.PENDING,
            schedule_id=schedule_id,
            next_run_at=next_run_at,
            error_message=None,
        )
        return await self.get(company_id, schedule_task_id)

    async def cancel(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self.get(company_id, schedule_task_id)
        if task.status not in (ScheduledTaskStatus.PENDING, ScheduledTaskStatus.PAUSED):
            raise ValueError(f"cannot cancel task with status={self._status_value(task.status)}")
        if task.schedule_id:
            source = get_schedule_source(self._redis_url)
            await source.startup()
            await source.delete_schedule(task.schedule_id)
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=ScheduledTaskStatus.CANCELLED,
            schedule_id=None,
        )
        return await self.get(company_id, schedule_task_id)

    async def run_now(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self.get(company_id, schedule_task_id)
        if task.status not in (ScheduledTaskStatus.PENDING, ScheduledTaskStatus.PAUSED):
            raise ValueError(f"cannot run-now task with status={self._status_value(task.status)}")
        broker = self._broker_for_queue(task.queue_name)
        kicker = AsyncKicker(
            task_name=task.task_name,
            broker=broker,
            labels=self._build_task_labels(task),
        )
        await kicker.kiq(**task.payload)
        next_run_at = task.next_run_at
        if task.schedule_type in (PlatformScheduleType.CRON, PlatformScheduleType.INTERVAL):
            next_run_at = self._calculate_next_run_at(task)
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=task.status,
            last_run_at=datetime.now(timezone.utc),
            next_run_at=next_run_at,
            error_message=None,
        )
        return await self.get(company_id, schedule_task_id)

    async def mark_failed(self, company_id: str, schedule_task_id: str, error_message: str) -> None:
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=ScheduledTaskStatus.FAILED,
            error_message=error_message,
        )

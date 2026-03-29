"""Сервис платформенного scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from taskiq.kicker import AsyncKicker

from core.scheduler.models import (
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

    def __init__(self, repository: SchedulerTaskRepository, broker: Any, redis_url: str) -> None:
        self._repository = repository
        self._broker = broker
        self._redis_url = redis_url

    async def _create_schedule(self, task: PlatformScheduledTask) -> str:
        source = get_schedule_source(self._redis_url)
        await source.startup()
        kicker = AsyncKicker(task_name=task.task_name, broker=self._broker, labels={})

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
            next_run_at=request.run_at,
        )
        task.payload["scheduler_task_id"] = task.id
        task.payload["company_id"] = company_id
        if task.schedule_type == PlatformScheduleType.INTERVAL:
            task.next_run_at = now + timedelta(seconds=task.interval_seconds or 0)
        task.schedule_id = await self._create_schedule(task)
        return await self._repository.save(task)

    async def get(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self._repository.get(company_id=company_id, schedule_task_id=schedule_task_id)
        if task is None:
            raise ValueError(f"schedule task not found: {schedule_task_id}")
        return task

    async def list(self, company_id: str, filters: PlatformScheduleFilter) -> list[PlatformScheduledTask]:
        return await self._repository.list(company_id=company_id, filters=filters)

    async def pause(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self.get(company_id, schedule_task_id)
        if task.status != ScheduledTaskStatus.PENDING:
            raise ValueError(f"task status must be pending, got {task.status.value}")
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
            raise ValueError(f"task status must be paused, got {task.status.value}")
        schedule_id = await self._create_schedule(task)
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=ScheduledTaskStatus.PENDING,
            schedule_id=schedule_id,
            error_message=None,
        )
        return await self.get(company_id, schedule_task_id)

    async def cancel(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask:
        task = await self.get(company_id, schedule_task_id)
        if task.status not in (ScheduledTaskStatus.PENDING, ScheduledTaskStatus.PAUSED):
            raise ValueError(f"cannot cancel task with status={task.status.value}")
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
            raise ValueError(f"cannot run-now task with status={task.status.value}")
        kicker = AsyncKicker(task_name=task.task_name, broker=self._broker, labels={})
        await kicker.kiq(**task.payload)
        await self._repository.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=task.status,
            last_run_at=datetime.now(timezone.utc),
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

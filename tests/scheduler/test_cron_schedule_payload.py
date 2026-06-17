"""Reconcile cron-расписаний с legacy kwargs в Redis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from apps.scheduler.main import (
    CALENDAR_SYNC_TASK_NAME,
    SYSTEM_SCHEDULER_COMPANY_ID,
    _ensure_calendar_schedule,
)
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)


class _InMemorySchedulerService:
    def __init__(self, tasks: list[PlatformScheduledTask] | None = None) -> None:
        self.tasks = list(tasks or [])
        self.created_requests: list[PlatformScheduleCreateRequest] = []
        self.reconciled_ids: list[str] = []

    async def list(
        self,
        *,
        company_id: str,
        filters: PlatformScheduleFilter,
    ) -> list[PlatformScheduledTask]:
        return [
            task
            for task in self.tasks
            if task.company_id == company_id
            and (filters.task_name is None or task.task_name == filters.task_name)
        ]

    async def create(
        self,
        *,
        company_id: str,
        user_id: str | None,
        request: PlatformScheduleCreateRequest,
    ) -> PlatformScheduledTask:
        self.created_requests.append(request)
        task = PlatformScheduledTask(
            schedule_task_id=f"created-{len(self.created_requests)}",
            company_id=company_id,
            schedule_id=f"redis-{len(self.created_requests)}",
            target_service=request.target_service,
            task_name=request.task_name,
            queue_name=request.queue_name,
            schedule_type=request.schedule_type,
            cron=request.cron,
            interval_seconds=request.interval_seconds,
            run_at=request.run_at,
            timezone=request.timezone,
            payload={
                **dict(request.payload),
                "schedule_task_id": f"created-{len(self.created_requests)}",
                "company_id": company_id,
            },
            status=ScheduledTaskStatus.PENDING,
            created_by_user_id=user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.tasks.append(task)
        return task

    async def resume(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> PlatformScheduledTask:
        raise AssertionError("resume should not be called in this test")

    async def get_redis_snapshot(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> PlatformRedisScheduleSnapshot:
        for task in self.tasks:
            if task.company_id == company_id and task.schedule_task_id == schedule_task_id:
                return PlatformRedisScheduleSnapshot(
                    schedule_task_id=task.schedule_task_id,
                    company_id=task.company_id,
                    schedule_id=task.schedule_id,
                    exists_in_redis=True,
                    status=task.status,
                    task_name=task.task_name,
                    cron=task.cron,
                    kwargs=task.payload,
                )
        raise AssertionError(f"task not found: {schedule_task_id}")

    async def reconcile_payload(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
        payload: dict[str, Any],
        recreate_schedule: bool = False,
    ) -> PlatformScheduledTask:
        self.reconciled_ids.append(schedule_task_id)
        for index, task in enumerate(self.tasks):
            if task.company_id == company_id and task.schedule_task_id == schedule_task_id:
                repaired = task.model_copy(
                    update={
                        "payload": {
                            **dict(payload),
                            "schedule_task_id": schedule_task_id,
                            "company_id": company_id,
                        }
                    }
                )
                self.tasks[index] = repaired
                return repaired
        raise AssertionError(f"task not found: {schedule_task_id}")


class _Container:
    def __init__(self, service: _InMemorySchedulerService) -> None:
        self.scheduler_service = service


def _task(
    schedule_task_id: str,
    *,
    status: ScheduledTaskStatus,
    cron: str = "0 * * * *",
    payload: dict[str, Any] | None = None,
) -> PlatformScheduledTask:
    return PlatformScheduledTask(
        schedule_task_id=schedule_task_id,
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        schedule_id=f"redis-{schedule_task_id}",
        target_service="flows",
        task_name=CALENDAR_SYNC_TASK_NAME,
        queue_name="idle",
        schedule_type=PlatformScheduleType.CRON,
        cron=cron,
        timezone="UTC",
        payload=payload or {},
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_ensure_calendar_schedule_reconciles_legacy_scheduler_task_id_payload() -> None:
    service = _InMemorySchedulerService(
        [
            _task(
                "calendar-sync-old",
                status=ScheduledTaskStatus.PENDING,
                payload={
                    "scheduler_task_id": "calendar-sync-old",
                    "company_id": SYSTEM_SCHEDULER_COMPANY_ID,
                },
            )
        ]
    )
    container = _Container(service)

    await _ensure_calendar_schedule(
        container=container,
        config_enabled=True,
        task_name=CALENDAR_SYNC_TASK_NAME,
        cron="0 * * * *",
        log_label="Calendar sync",
    )

    assert service.created_requests == []
    assert service.reconciled_ids == ["calendar-sync-old"]
    assert service.tasks[0].payload == {
        "schedule_task_id": "calendar-sync-old",
        "company_id": SYSTEM_SCHEDULER_COMPANY_ID,
    }

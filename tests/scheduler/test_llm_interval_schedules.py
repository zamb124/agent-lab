"""Scheduler bootstrap coverage for LLM background schedules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from apps.scheduler.main import (
    OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER,
    OPENROUTER_FREE_MODELS_SYNC_TASK_NAME,
    SYSTEM_SCHEDULER_COMPANY_ID,
    _ensure_idle_interval_schedule,
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
        self.resumed_ids: list[str] = []
        self.run_now_ids: list[str] = []
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
        )
        self.tasks.append(task)
        return task

    async def resume(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> PlatformScheduledTask:
        self.resumed_ids.append(schedule_task_id)
        for index, task in enumerate(self.tasks):
            if task.company_id == company_id and task.schedule_task_id == schedule_task_id:
                resumed = task.model_copy(update={"status": ScheduledTaskStatus.PENDING})
                self.tasks[index] = resumed
                return resumed
        raise AssertionError(f"task not found: {schedule_task_id}")

    async def get_redis_snapshot(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> PlatformRedisScheduleSnapshot:
        for task in self.tasks:
            if task.company_id == company_id and task.schedule_task_id == schedule_task_id:
                if task.schedule_id is None:
                    return PlatformRedisScheduleSnapshot(
                        schedule_task_id=task.schedule_task_id,
                        company_id=task.company_id,
                        schedule_id=None,
                        exists_in_redis=False,
                        status=task.status,
                        task_name=task.task_name,
                    )
                return PlatformRedisScheduleSnapshot(
                    schedule_task_id=task.schedule_task_id,
                    company_id=task.company_id,
                    schedule_id=task.schedule_id,
                    exists_in_redis=True,
                    status=task.status,
                    task_name=task.task_name,
                    interval_seconds=task.interval_seconds,
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
                schedule_id = task.schedule_id
                if recreate_schedule:
                    schedule_id = f"redis-reconciled-{schedule_task_id}"
                repaired = task.model_copy(
                    update={
                        "schedule_id": schedule_id,
                        "payload": {
                            **dict(payload),
                            "schedule_task_id": schedule_task_id,
                            "company_id": company_id,
                        },
                    }
                )
                self.tasks[index] = repaired
                return repaired
        raise AssertionError(f"task not found: {schedule_task_id}")

    async def run_now(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> None:
        assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
        self.run_now_ids.append(schedule_task_id)


class _Container:
    def __init__(self, scheduler_service: _InMemorySchedulerService) -> None:
        self.scheduler_service = scheduler_service


def _task(
    schedule_task_id: str,
    *,
    status: ScheduledTaskStatus,
    interval_seconds: int,
    task_name: str = OPENROUTER_FREE_MODELS_SYNC_TASK_NAME,
    payload: dict[str, Any] | None = None,
) -> PlatformScheduledTask:
    return PlatformScheduledTask(
        schedule_task_id=schedule_task_id,
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        schedule_id=f"redis-{schedule_task_id}",
        target_service="flows",
        task_name=task_name,
        queue_name="idle",
        schedule_type=PlatformScheduleType.INTERVAL,
        interval_seconds=interval_seconds,
        run_at=datetime.now(timezone.utc),
        timezone="UTC",
        payload=payload or {},
        status=status,
    )


@pytest.mark.asyncio
async def test_ensure_idle_interval_schedule_creates_idle_schedule_and_kicks_it() -> None:
    service = _InMemorySchedulerService()
    container = _Container(service)

    await _ensure_idle_interval_schedule(
        container=container,
        config_enabled=True,
        task_name=OPENROUTER_FREE_MODELS_SYNC_TASK_NAME,
        interval_seconds=3300,
        payload={"system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER},
        log_label="OpenRouter free-pool sync",
        run_now_on_start=True,
    )

    assert len(service.created_requests) == 1
    request = service.created_requests[0]
    assert request.target_service == "flows"
    assert request.queue_name == "idle"
    assert request.schedule_type == PlatformScheduleType.INTERVAL
    assert request.interval_seconds == 3300
    assert request.payload == {"system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER}
    assert request.run_at is not None and request.run_at.tzinfo is not None
    assert service.run_now_ids == ["created-1"]


@pytest.mark.asyncio
async def test_ensure_idle_interval_schedule_resumes_compatible_paused_schedule() -> None:
    service = _InMemorySchedulerService(
        [
            _task(
                "paused-compatible",
                status=ScheduledTaskStatus.PAUSED,
                interval_seconds=3300,
            )
        ]
    )
    container = _Container(service)

    await _ensure_idle_interval_schedule(
        container=container,
        config_enabled=True,
        task_name=OPENROUTER_FREE_MODELS_SYNC_TASK_NAME,
        interval_seconds=3300,
        payload={"system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER},
        log_label="OpenRouter free-pool sync",
        run_now_on_start=True,
    )

    assert service.created_requests == []
    assert service.resumed_ids == ["paused-compatible"]
    assert service.run_now_ids == ["paused-compatible"]
    assert service.tasks[0].status == ScheduledTaskStatus.PENDING


@pytest.mark.asyncio
async def test_ensure_idle_interval_schedule_leaves_incompatible_pending_and_creates_current_one() -> None:
    service = _InMemorySchedulerService(
        [
            _task(
                "old-interval",
                status=ScheduledTaskStatus.PENDING,
                interval_seconds=60,
            )
        ]
    )
    container = _Container(service)

    await _ensure_idle_interval_schedule(
        container=container,
        config_enabled=True,
        task_name=OPENROUTER_FREE_MODELS_SYNC_TASK_NAME,
        interval_seconds=3300,
        payload={"system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER},
        log_label="OpenRouter free-pool sync",
        run_now_on_start=True,
    )

    assert [task.schedule_task_id for task in service.tasks] == ["old-interval", "created-1"]
    assert service.tasks[0].status == ScheduledTaskStatus.PENDING
    assert service.created_requests[0].interval_seconds == 3300
    assert service.run_now_ids == ["created-1"]


@pytest.mark.asyncio
async def test_ensure_idle_interval_schedule_reconciles_legacy_payload_without_task_fallback() -> None:
    service = _InMemorySchedulerService(
        [
            _task(
                "old-interval",
                status=ScheduledTaskStatus.PENDING,
                interval_seconds=3300,
                payload={
                    "system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER,
                    "scheduler_task_id": "old-interval",
                    "company_id": SYSTEM_SCHEDULER_COMPANY_ID,
                },
            )
        ]
    )
    container = _Container(service)

    await _ensure_idle_interval_schedule(
        container=container,
        config_enabled=True,
        task_name=OPENROUTER_FREE_MODELS_SYNC_TASK_NAME,
        interval_seconds=3300,
        payload={"system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER},
        log_label="OpenRouter free-pool sync",
        run_now_on_start=True,
    )

    assert service.created_requests == []
    assert service.reconciled_ids == ["old-interval"]
    assert service.run_now_ids == ["old-interval"]
    assert service.tasks[0].payload == {
        "system_task": OPENROUTER_FREE_MODELS_SYNC_PAYLOAD_MARKER,
        "schedule_task_id": "old-interval",
        "company_id": SYSTEM_SCHEDULER_COMPANY_ID,
    }

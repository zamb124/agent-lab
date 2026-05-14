"""Тесты расчета next_run_at в SchedulerService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from taskiq.scheduler.scheduled_task import ScheduledTask

from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.scheduler.service import SchedulerService


class _InMemorySchedulerRepository:
    def __init__(self, task: PlatformScheduledTask | None = None) -> None:
        self.task = task
        self.updated_next_run_at: Optional[datetime] = None

    async def save(self, task: PlatformScheduledTask) -> PlatformScheduledTask:
        self.task = task
        return task

    async def get(self, company_id: str, schedule_task_id: str) -> PlatformScheduledTask | None:
        if self.task is None:
            return None
        if self.task.company_id != company_id:
            return None
        if self.task.id != schedule_task_id:
            return None
        return self.task

    async def list(self, company_id: str, filters: PlatformScheduleFilter) -> list[PlatformScheduledTask]:
        if self.task is None:
            return []
        if self.task.company_id != company_id:
            return []
        return [self.task]

    async def update_status(
        self,
        company_id: str,
        schedule_task_id: str,
        status: ScheduledTaskStatus,
        *,
        schedule_id: str | None = None,
        last_run_at: datetime | None = None,
        next_run_at: datetime | None = None,
        error_message: str | None = None,
    ) -> bool:
        if self.task is None:
            return False
        if self.task.company_id != company_id or self.task.id != schedule_task_id:
            return False
        self.task.status = status
        if schedule_id is not None:
            self.task.schedule_id = schedule_id
        if last_run_at is not None:
            self.task.last_run_at = last_run_at
        if next_run_at is not None:
            self.task.next_run_at = next_run_at
            self.updated_next_run_at = next_run_at
        if error_message is not None:
            self.task.error_message = error_message
        self.task.updated_at = datetime.now(timezone.utc)
        return True


class _FakeScheduleSource:
    def __init__(self, schedules: list[ScheduledTask]) -> None:
        self._schedules = schedules

    async def startup(self) -> None:
        return None

    async def get_schedules(self) -> list[ScheduledTask]:
        return self._schedules


@pytest.mark.asyncio
async def test_create_cron_schedule_sets_next_run_at() -> None:
    repository = _InMemorySchedulerRepository()
    service = SchedulerService(
        repository=repository,
        redis_url="redis://localhost:6379/0",
        broker_for_queue=lambda _q: object(),
    )

    async def _fake_create_schedule(task: PlatformScheduledTask) -> str:
        return "schedule-1"

    service._create_schedule = _fake_create_schedule  # type: ignore[method-assign]

    before_create = datetime.now(timezone.utc)
    request = PlatformScheduleCreateRequest(
        target_service="flows",
        task_name="calendar_sync_tick",
        schedule_type=PlatformScheduleType.CRON,
        cron="*/1 * * * *",
        timezone="UTC",
        payload={},
    )
    created = await service.create(company_id="system", user_id=None, request=request)

    assert created.next_run_at is not None
    assert created.next_run_at > before_create
    assert created.next_run_at <= before_create + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_list_enriches_missing_next_run_at_for_pending_cron() -> None:
    task = PlatformScheduledTask(
        id="task-1",
        company_id="system",
        schedule_id="schedule-1",
        target_service="flows",
        task_name="calendar_sync_tick",
        queue_name=None,
        schedule_type=PlatformScheduleType.CRON,
        cron="*/1 * * * *",
        interval_seconds=None,
        run_at=None,
        timezone="UTC",
        payload={},
        status=ScheduledTaskStatus.PENDING,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=None,
        error_message=None,
    )
    repository = _InMemorySchedulerRepository(task=task)
    service = SchedulerService(
        repository=repository,
        redis_url="redis://localhost:6379/0",
        broker_for_queue=lambda _q: object(),
    )

    items = await service.list(company_id="system", filters=PlatformScheduleFilter())

    assert len(items) == 1
    assert items[0].next_run_at is not None


@pytest.mark.asyncio
async def test_resume_cron_schedule_updates_next_run_at() -> None:
    task = PlatformScheduledTask(
        id="task-1",
        company_id="system",
        schedule_id=None,
        target_service="flows",
        task_name="calendar_sync_tick",
        queue_name=None,
        schedule_type=PlatformScheduleType.CRON,
        cron="*/1 * * * *",
        interval_seconds=None,
        run_at=None,
        timezone="UTC",
        payload={},
        status=ScheduledTaskStatus.PAUSED,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=None,
        error_message=None,
    )
    repository = _InMemorySchedulerRepository(task=task)
    service = SchedulerService(
        repository=repository,
        redis_url="redis://localhost:6379/0",
        broker_for_queue=lambda _q: object(),
    )

    async def _fake_create_schedule(task: PlatformScheduledTask) -> str:
        return "schedule-2"

    service._create_schedule = _fake_create_schedule  # type: ignore[method-assign]

    resumed = await service.resume(company_id="system", schedule_task_id="task-1")

    assert repository.updated_next_run_at is not None
    assert resumed.next_run_at is not None
    assert resumed.schedule_id == "schedule-2"
    assert resumed.status == ScheduledTaskStatus.PENDING


@pytest.mark.asyncio
async def test_get_redis_snapshot_returns_taskiq_schedule_data(monkeypatch: pytest.MonkeyPatch) -> None:
    task = PlatformScheduledTask(
        id="task-1",
        company_id="system",
        schedule_id="schedule-redis-1",
        target_service="flows",
        task_name="sync_llm_models_task",
        queue_name="idle",
        schedule_type=PlatformScheduleType.INTERVAL,
        cron=None,
        interval_seconds=60,
        run_at=None,
        timezone="UTC",
        payload={},
        status=ScheduledTaskStatus.PENDING,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=None,
        error_message=None,
    )
    repository = _InMemorySchedulerRepository(task=task)
    service = SchedulerService(
        repository=repository,
        redis_url="redis://localhost:6379/0",
        broker_for_queue=lambda _q: object(),
    )
    redis_schedule = ScheduledTask(
        task_name="sync_llm_models_task",
        labels={"source": "taskiq"},
        args=[],
        kwargs={"scheduler_task_id": "task-1"},
        task_id="message-1",
        schedule_id="schedule-redis-1",
        cron=None,
        cron_offset=None,
        time=None,
        interval=60,
    )
    fake_source = _FakeScheduleSource(schedules=[redis_schedule])
    monkeypatch.setattr("core.scheduler.service.get_schedule_source", lambda redis_url: fake_source)

    snapshot = await service.get_redis_snapshot(company_id="system", schedule_task_id="task-1")

    assert snapshot.exists_in_redis is True
    assert snapshot.schedule_id == "schedule-redis-1"
    assert snapshot.interval_seconds == 60
    assert snapshot.taskiq_task_id == "message-1"
    assert snapshot.kwargs["scheduler_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_get_redis_snapshot_handles_missing_schedule_id_without_redis_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = PlatformScheduledTask(
        id="task-2",
        company_id="system",
        schedule_id=None,
        target_service="flows",
        task_name="calendar_sync_tick",
        queue_name=None,
        schedule_type=PlatformScheduleType.CRON,
        cron="*/1 * * * *",
        interval_seconds=None,
        run_at=None,
        timezone="UTC",
        payload={},
        status=ScheduledTaskStatus.PAUSED,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=None,
        error_message=None,
    )
    repository = _InMemorySchedulerRepository(task=task)
    service = SchedulerService(
        repository=repository,
        redis_url="redis://localhost:6379/0",
        broker_for_queue=lambda _q: object(),
    )
    monkeypatch.setattr(
        "core.scheduler.service.get_schedule_source",
        lambda redis_url: (_ for _ in ()).throw(RuntimeError("redis access is not expected")),
    )

    snapshot = await service.get_redis_snapshot(company_id="system", schedule_task_id="task-2")

    assert snapshot.exists_in_redis is False
    assert snapshot.missing_reason == "schedule_id is null"


@pytest.mark.asyncio
async def test_run_now_adds_required_logging_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    task = PlatformScheduledTask(
        id="task-run-now",
        company_id="system",
        schedule_id="schedule-run-now",
        target_service="flows",
        task_name="sync_llm_models_task",
        queue_name="idle",
        schedule_type=PlatformScheduleType.INTERVAL,
        cron=None,
        interval_seconds=60,
        run_at=None,
        timezone="UTC",
        payload={"scheduler_task_id": "task-run-now", "company_id": "system"},
        status=ScheduledTaskStatus.PENDING,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        error_message=None,
    )
    repository = _InMemorySchedulerRepository(task=task)
    service = SchedulerService(
        repository=repository,
        redis_url="redis://localhost:6379/0",
        broker_for_queue=lambda _q: object(),
    )
    captured_labels: dict[str, str] = {}

    class _FakeKicker:
        def __init__(self, task_name: str, broker, labels: dict[str, str]) -> None:
            _ = broker
            assert task_name == "sync_llm_models_task"
            captured_labels.update(labels)

        async def kiq(self, **kwargs) -> None:
            assert kwargs["scheduler_task_id"] == "task-run-now"

    monkeypatch.setattr("core.scheduler.service.AsyncKicker", _FakeKicker)
    monkeypatch.setattr(
        "core.scheduler.service.build_log_labels",
        lambda *, background_kind: {
            "request_id": "req-1",
            "trace_id": "trace-1",
            "service_name": "scheduler",
        },
    )

    await service.run_now(company_id="system", schedule_task_id="task-run-now")

    assert captured_labels["queue_name"] == "idle"
    assert captured_labels["request_id"] == "req-1"
    assert captured_labels["trace_id"] == "trace-1"
    assert captured_labels["service_name"] == "scheduler"

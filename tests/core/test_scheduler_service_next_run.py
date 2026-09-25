"""Тесты расчета next_run_at в SchedulerService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import override

import pytest
from taskiq import InMemoryBroker
from taskiq.abc.broker import AsyncBroker
from taskiq.scheduler.scheduled_task import ScheduledTask

from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.scheduler.service import SchedulerService


def _broker(queue_name: str) -> AsyncBroker:
    _ = queue_name
    return InMemoryBroker()


class _FixedScheduleService(SchedulerService):
    def __init__(self, schedule_id: str) -> None:
        super().__init__(redis_url="redis://localhost:6379/0", broker_for_queue=_broker)
        self._schedule_id: str = schedule_id

    @override
    async def _create_schedule(self, task: PlatformScheduledTask) -> str:
        _ = task
        return self._schedule_id


class _FakeScheduleSource:
    def __init__(self, schedules: list[ScheduledTask]) -> None:
        self._schedules: list[ScheduledTask] = schedules

    async def startup(self) -> None:
        return None

    async def get_schedules(self) -> list[ScheduledTask]:
        return self._schedules


@pytest.mark.asyncio
async def test_create_cron_schedule_sets_next_run_at() -> None:
    service = _FixedScheduleService("schedule-1")

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
        schedule_task_id="task-1",
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
    _ = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    service = SchedulerService(
        redis_url="redis://localhost:6379/0",
        broker_for_queue=_broker,
    )

    items = await service.list(company_id="system", filters=PlatformScheduleFilter())
    saved = [item for item in items if item.schedule_task_id == task.schedule_task_id]

    assert len(saved) == 1
    assert saved[0].next_run_at is not None


@pytest.mark.asyncio
async def test_resume_cron_schedule_updates_next_run_at() -> None:
    task = PlatformScheduledTask(
        schedule_task_id="task-1",
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
    _ = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    service = _FixedScheduleService("schedule-2")

    resumed = await service.resume(company_id="system", schedule_task_id="task-1")

    assert resumed.next_run_at is not None
    assert resumed.schedule_id == "schedule-2"
    assert resumed.status == ScheduledTaskStatus.PENDING


@pytest.mark.asyncio
async def test_get_redis_snapshot_returns_taskiq_schedule_data(monkeypatch: pytest.MonkeyPatch) -> None:
    task = PlatformScheduledTask(
        schedule_task_id="task-1",
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
    _ = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    service = SchedulerService(
        redis_url="redis://localhost:6379/0",
        broker_for_queue=_broker,
    )
    redis_schedule = ScheduledTask(
        task_name="sync_llm_models_task",
        labels={"source": "taskiq"},
        args=[],
        kwargs={"schedule_task_id": "task-1"},
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
    assert snapshot.kwargs["schedule_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_get_redis_snapshot_handles_missing_schedule_id_without_redis_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = PlatformScheduledTask(
        schedule_task_id="task-2",
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
    _ = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    service = SchedulerService(
        redis_url="redis://localhost:6379/0",
        broker_for_queue=_broker,
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
        schedule_task_id="task-run-now",
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
        payload={"schedule_task_id": "task-run-now", "company_id": "system"},
        status=ScheduledTaskStatus.PENDING,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        error_message=None,
    )
    _ = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    service = SchedulerService(
        redis_url="redis://localhost:6379/0",
        broker_for_queue=_broker,
    )
    captured_labels: dict[str, str] = {}

    class _FakeKicker:
        def __init__(self, task_name: str, broker, labels: dict[str, str]) -> None:
            _ = broker
            assert task_name == "sync_llm_models_task"
            captured_labels.update(labels)

        async def kiq(self, **kwargs) -> None:
            assert kwargs["schedule_task_id"] == "task-run-now"

    monkeypatch.setattr("core.scheduler.service.AsyncKicker", _FakeKicker)
    monkeypatch.setattr(
        "core.scheduler.service.build_log_labels",
        lambda *, background_kind: {
            "request_id": "req-1",
            "trace_id": "trace-1",
            "service_name": "scheduler",
        },
    )

    _ = await service.run_now(company_id="system", schedule_task_id="task-run-now")

    assert captured_labels["queue_name"] == "idle"
    assert captured_labels["request_id"] == "req-1"
    assert captured_labels["trace_id"] == "trace-1"
    assert captured_labels["service_name"] == "scheduler"


@pytest.mark.asyncio
async def test_run_now_forwards_canonical_schedule_task_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    task = PlatformScheduledTask(
        schedule_task_id="task-run-now",
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
        payload={"schedule_task_id": "task-run-now", "company_id": "system"},
        status=ScheduledTaskStatus.PENDING,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_run_at=None,
        next_run_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        error_message=None,
    )
    _ = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    service = SchedulerService(
        redis_url="redis://localhost:6379/0",
        broker_for_queue=_broker,
    )
    captured_kwargs: dict[str, str] = {}

    class _FakeKicker:
        def __init__(self, task_name: str, broker, labels: dict[str, str]) -> None:
            del broker, labels
            assert task_name == "sync_llm_models_task"

        async def kiq(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr("core.scheduler.service.AsyncKicker", _FakeKicker)
    monkeypatch.setattr(
        "core.scheduler.service.build_log_labels",
        lambda *, background_kind: {
            "request_id": "req-1",
            "trace_id": "trace-1",
            "service_name": "scheduler",
        },
    )

    _ = await service.run_now(company_id="system", schedule_task_id="task-run-now")

    assert captured_kwargs == {
        "schedule_task_id": "task-run-now",
        "company_id": "system",
    }


def _schedule_task(
    *,
    schedule_task_id: str,
    company_id: str,
    task_name: str,
    created_at: datetime,
) -> PlatformScheduledTask:
    return PlatformScheduledTask(
        schedule_task_id=schedule_task_id,
        company_id=company_id,
        schedule_id=None,
        target_service="flows",
        task_name=task_name,
        queue_name=None,
        schedule_type=PlatformScheduleType.CRON,
        cron="*/1 * * * *",
        interval_seconds=None,
        run_at=None,
        timezone="UTC",
        payload={},
        status=ScheduledTaskStatus.PENDING,
        created_by_user_id=None,
        created_at=created_at,
        updated_at=created_at,
        last_run_at=None,
        next_run_at=None,
        error_message=None,
    )


@pytest.mark.asyncio
async def test_upsert_by_schedule_task_id_updates_same_row(unique_id: str) -> None:
    schedule_task_id = f"{unique_id}_schedule"
    created_at = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    task = _schedule_task(
        schedule_task_id=schedule_task_id,
        company_id="system",
        task_name="first",
        created_at=created_at,
    )
    inserted = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    assert inserted.schedule_task_id == schedule_task_id
    task.task_name = "second"
    updated = await PlatformScheduledTask.upsert_by_schedule_task_id(task)
    assert updated.schedule_task_id == schedule_task_id
    stored = await PlatformScheduledTask.find_in_company("system", schedule_task_id)
    assert stored is not None
    assert stored.task_name == "second"
    assert stored.created_at == created_at
    assert await PlatformScheduledTask.find_in_company(f"{unique_id}_other", schedule_task_id) is None
    with pytest.raises(ValueError, match="schedule_task_id cannot be empty"):
        _ = await PlatformScheduledTask.upsert_by_schedule_task_id(
            _schedule_task(
                schedule_task_id="",
                company_id="system",
                task_name="empty",
                created_at=created_at,
            )
        )

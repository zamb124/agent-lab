"""Scheduler dispatch compatibility coverage."""

from __future__ import annotations

from typing import Any

import pytest
from taskiq.scheduler.scheduled_task import ScheduledTask

from apps.scheduler import dispatch as scheduler_dispatch


class _FakeScheduleSource:
    def __init__(self) -> None:
        self.pre_sent: list[str] = []
        self.post_sent: list[str] = []

    async def pre_send(self, task: ScheduledTask) -> None:
        self.pre_sent.append(task.schedule_id)

    async def post_send(self, task: ScheduledTask) -> None:
        self.post_sent.append(task.schedule_id)


def _scheduled_task(kwargs: dict[str, Any]) -> ScheduledTask:
    return ScheduledTask(
        task_name="sync_llm_models_task",
        labels={"queue_name": "idle"},
        args=[],
        kwargs=kwargs,
        task_id="taskiq-message-1",
        schedule_id="redis-schedule-1",
        cron=None,
        cron_offset=None,
        time=None,
        interval=60,
    )


@pytest.mark.asyncio
async def test_dispatch_normalizes_legacy_scheduler_task_id_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeKicker:
        def __init__(self, task_name: str, broker: Any, labels: dict[str, Any]) -> None:
            captured["task_name"] = task_name
            captured["broker"] = broker
            captured["labels"] = dict(labels)

        def with_labels(self, **labels: Any) -> "_FakeKicker":
            captured["with_labels"] = labels
            return self

        def with_task_id(self, task_id: str) -> "_FakeKicker":
            captured["task_id"] = task_id
            return self

        async def kiq(self, *args: Any, **kwargs: Any) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(scheduler_dispatch, "AsyncKicker", _FakeKicker)

    source = _FakeScheduleSource()
    scheduler = object.__new__(scheduler_dispatch.QueueAwareTaskiqScheduler)
    await scheduler.on_ready(
        source,
        _scheduled_task(
            {
                "scheduler_task_id": "legacy-schedule-id",
                "company_id": "system",
            }
        ),
    )

    assert captured["task_name"] == "sync_llm_models_task"
    assert captured["task_id"] == "taskiq-message-1"
    assert captured["args"] == ()
    assert captured["kwargs"] == {
        "schedule_task_id": "legacy-schedule-id",
        "company_id": "system",
    }
    assert source.pre_sent == ["redis-schedule-1"]
    assert source.post_sent == ["redis-schedule-1"]


@pytest.mark.asyncio
async def test_dispatch_drops_legacy_scheduler_task_id_when_canonical_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeKicker:
        def __init__(self, task_name: str, broker: Any, labels: dict[str, Any]) -> None:
            del task_name, broker, labels

        def with_labels(self, **labels: Any) -> "_FakeKicker":
            return self

        def with_task_id(self, task_id: str) -> "_FakeKicker":
            return self

        async def kiq(self, *args: Any, **kwargs: Any) -> None:
            del args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(scheduler_dispatch, "AsyncKicker", _FakeKicker)

    source = _FakeScheduleSource()
    scheduler = object.__new__(scheduler_dispatch.QueueAwareTaskiqScheduler)
    await scheduler.on_ready(
        source,
        _scheduled_task(
            {
                "scheduler_task_id": "legacy-schedule-id",
                "schedule_task_id": "canonical-schedule-id",
            }
        ),
    )

    assert captured["kwargs"] == {"schedule_task_id": "canonical-schedule-id"}

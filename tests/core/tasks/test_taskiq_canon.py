"""Unit-тесты единого TaskIQ-канона: registry, enqueue labels, wiring."""

from __future__ import annotations

import uuid

import pytest
from taskiq import InMemoryBroker

from apps.platform_tasks.wiring import all_queues, wire_all, wire_brokers, wire_worker
from core.tasks import (
    TaskPriority,
    TaskSpec,
    all_task_specs,
    declare_task,
    enqueue,
    get_task_spec,
    platform_task,
    register_queue_broker,
    registered_queue_brokers,
    scheduled_task_specs,
)
from core.tasks import kicker as kicker_module
from core.tasks.log_labels import LABEL_PRIORITY, LABEL_QUEUE_NAME, build_log_labels
from core.tasks.registry import queue_broker

pytestmark = pytest.mark.real_taskiq


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def test_declare_task_rejects_non_snake_case() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        _ = declare_task("Bad.Name", queue="idle")


def test_declare_task_rejects_empty_queue() -> None:
    with pytest.raises(ValueError, match="queue обязателен"):
        _ = declare_task(_unique("empty_queue_task"), queue="  ")


def test_declare_task_idempotent_same_spec() -> None:
    name = _unique("idempotent_task")
    first = declare_task(name, queue="idle", scheduled=False, retry=True, max_retries=2)
    second = declare_task(name, queue="idle", scheduled=False, retry=True, max_retries=2)
    assert first is second
    assert get_task_spec(name) == first


def test_declare_task_conflict_raises() -> None:
    name = _unique("conflict_task")
    _ = declare_task(name, queue="idle", scheduled=False)
    with pytest.raises(ValueError, match="уже объявлена иначе"):
        _ = declare_task(name, queue="idle", scheduled=True)


def test_get_task_spec_unknown_raises() -> None:
    with pytest.raises(ValueError, match="не объявлена"):
        _ = get_task_spec(_unique("missing_task"))


def test_platform_task_requires_registered_broker() -> None:
    name = _unique("no_broker_task")
    queue = _unique("orphan_queue")
    spec = declare_task(name, queue=queue)

    def _bind() -> None:
        @platform_task(spec)
        async def _orphan() -> None:
            return None

        _ = _orphan

    with pytest.raises(RuntimeError, match="не зарегистрирован"):
        _bind()


def test_platform_task_binds_to_inmemory_broker() -> None:
    name = _unique("bound_task")
    queue = _unique("bound_queue")
    spec = declare_task(name, queue=queue)
    broker = InMemoryBroker()
    register_queue_broker(queue, broker)

    @platform_task(spec)
    async def bound_task(value: str) -> str:
        return value

    found = broker.find_task(name)
    assert found is not None
    _ = bound_task
    assert queue_broker(queue) is broker


@pytest.mark.asyncio
async def test_enqueue_attaches_queue_and_priority_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = _unique("enqueue_labels")
    _ = declare_task(name, queue="idle")
    captured_task_name: list[str] = []
    captured_labels: list[dict[str, str]] = []
    captured_args: list[tuple[object, ...]] = []
    captured_kwargs: list[dict[str, object]] = []

    class _FakeKicker:
        def __init__(self, task_name: str, broker: object, labels: dict[str, str]) -> None:
            _ = broker
            captured_task_name.append(task_name)
            captured_labels.append(dict(labels))

        async def kiq(self, *args: object, **kwargs: object) -> dict[str, bool]:
            captured_args.append(args)
            captured_kwargs.append(dict(kwargs))
            return {"ok": True}

    def _fake_resolve(spec: TaskSpec | str) -> object:
        _ = get_task_spec(spec)
        return object()

    monkeypatch.setattr(kicker_module, "AsyncKicker", _FakeKicker)
    monkeypatch.setattr(kicker_module, "resolve_broker_for_task", _fake_resolve)

    result = await enqueue(
        name,
        "arg1",
        foo="bar",
        priority=TaskPriority.HIGH,
        background_kind="test",
    )

    assert result == {"ok": True}
    assert captured_task_name == [name]
    labels = captured_labels[0]
    assert labels[LABEL_QUEUE_NAME] == "idle"
    assert labels[LABEL_PRIORITY] == str(int(TaskPriority.HIGH))
    assert captured_args == [("arg1",)]
    assert captured_kwargs == [{"foo": "bar"}]
    assert "request_id" in labels
    assert "trace_id" in labels


@pytest.mark.asyncio
async def test_enqueue_sets_taskiq_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = _unique("enqueue_taskiq_id")
    _ = declare_task(name, queue="idle")
    captured_taskiq_task_id: list[str | None] = []

    class _FakeKicker:
        def __init__(self, task_name: str, broker: object, labels: dict[str, str]) -> None:
            _ = task_name
            _ = broker
            _ = labels
            self._taskiq_task_id: str | None = None

        def with_task_id(self, task_id: str | None) -> "_FakeKicker":
            self._taskiq_task_id = task_id
            return self

        async def kiq(self, *args: object, **kwargs: object) -> dict[str, bool]:
            _ = args
            _ = kwargs
            captured_taskiq_task_id.append(self._taskiq_task_id)
            return {"ok": True}

    def _fake_resolve(spec: TaskSpec | str) -> object:
        _ = get_task_spec(spec)
        return object()

    monkeypatch.setattr(kicker_module, "AsyncKicker", _FakeKicker)
    monkeypatch.setattr(kicker_module, "resolve_broker_for_task", _fake_resolve)

    result = await enqueue(
        name,
        "arg1",
        background_kind="test",
        taskiq_task_id="evaluation-run:abc",
    )
    assert result == {"ok": True}
    assert captured_taskiq_task_id == ["evaluation-run:abc"]


@pytest.mark.asyncio
async def test_enqueue_rejects_blank_taskiq_task_id() -> None:
    with pytest.raises(ValueError, match="taskiq_task_id пустой"):
        _ = await enqueue("unused_task_never_resolved", taskiq_task_id="   ")


def test_build_log_labels_rejects_empty_override() -> None:
    with pytest.raises(ValueError):
        _ = build_log_labels(override_request_id="")


def test_wire_all_covers_declared_queues() -> None:
    wire_all()
    known = set(all_queues())
    brokers = set(registered_queue_brokers())
    assert known.issubset(brokers)
    for spec in all_task_specs():
        if spec.queue in known:
            assert spec.queue in brokers


def test_require_scheduled_tasks_registered_after_wire_all() -> None:
    wire_all()
    # Только канонические очереди wiring — тестовые declare_task не в topology.
    known = set(all_queues())
    platform_scheduled = [spec for spec in scheduled_task_specs() if spec.queue in known]
    assert platform_scheduled
    brokers = registered_queue_brokers()
    missing = [
        f"{spec.queue}:{spec.name}"
        for spec in platform_scheduled
        if brokers.get(spec.queue) is None or brokers[spec.queue].find_task(spec.name) is None
    ]
    assert missing == []


def test_wire_worker_returns_queue_broker() -> None:
    broker = wire_worker("rag")
    assert registered_queue_brokers()["rag"] is broker


def test_wire_brokers_registers_all_queues() -> None:
    wire_brokers()
    assert set(registered_queue_brokers()) >= set(all_queues())


def test_task_spec_equality_and_hash() -> None:
    left = TaskSpec(name="sample_task", queue="idle", scheduled=True, retry=True, max_retries=5)
    right = TaskSpec(name="sample_task", queue="idle", scheduled=True, retry=True, max_retries=5)
    other = TaskSpec(name="sample_task", queue="idle", scheduled=False, retry=True, max_retries=5)
    assert left == right
    assert hash(left) == hash(right)
    assert left != other

"""Реестр TaskIQ после wire_all: specs, брокеры, scheduled."""

import pytest

from apps.worker_manifest import all_queues, wire_all
from core.tasks import all_task_specs, registered_queue_brokers, scheduled_task_specs

pytestmark = pytest.mark.real_taskiq


def test_wire_all_registers_specs_and_scheduled_on_brokers() -> None:
    wire_all()
    specs = all_task_specs()
    brokers = registered_queue_brokers()
    known_queues = set(all_queues())

    assert specs
    assert known_queues.issubset(set(brokers))

    names = [spec.name for spec in specs]
    assert len(names) == len(set(names))

    for spec in specs:
        if spec.queue not in known_queues:
            continue
        assert spec.queue in brokers
        assert spec.name == spec.name.strip()
        assert spec.name.replace("_", "").isalnum()
        assert spec.name[0].islower()

    for spec in scheduled_task_specs():
        if spec.queue not in known_queues:
            continue
        broker = brokers[spec.queue]
        assert broker.find_task(spec.name) is not None, f"{spec.queue}:{spec.name}"

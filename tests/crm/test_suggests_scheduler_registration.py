"""Регистрация CRM scheduled-задач в едином TaskIQ-реестре."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

import pytest

from apps.crm_worker.tasks.task_names import (
    CRM_GENERATE_NAMESPACE_SUGGESTS,
    CRM_RECONCILE_DAILY_SUMMARY,
    CRM_REEMBED_STALE_DOCUMENTS,
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC,
)
from apps.platform_tasks.wiring import all_queues, wire_all, wire_worker
from core.tasks import registered_queue_brokers, scheduled_task_specs

pytestmark = pytest.mark.real_taskiq

# Impl-модули требуют брокер очереди до import (@platform_task).
_ = wire_worker("crm")

from apps.crm_worker.tasks.daily_summary_tasks import (  # noqa: E402
    reconcile_daily_summary_task,
)
from apps.crm_worker.tasks.reembed_tasks import (  # noqa: E402
    crm_reembed_stale_documents_tick,
)
from apps.crm_worker.tasks.scheduled_integration_sync_tasks import (  # noqa: E402
    scheduled_namespace_integration_unified_sync,
)
from apps.crm_worker.tasks.suggest_tasks import (  # noqa: E402
    crm_generate_namespace_suggests_tick,
)

CRM_SCHEDULER_TASK_NAMES = (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC.name,
    CRM_REEMBED_STALE_DOCUMENTS.name,
    CRM_GENERATE_NAMESPACE_SUGGESTS.name,
    CRM_RECONCILE_DAILY_SUMMARY.name,
)


def _task_signature(task: object) -> inspect.Signature:
    wrapped = cast(Callable[..., object], task)
    unwrapped = cast(Callable[..., object], inspect.unwrap(wrapped))
    return inspect.signature(unwrapped)


def test_crm_scheduler_tasks_are_registered_for_scheduler() -> None:
    wire_all()
    scheduled_names = {spec.name for spec in scheduled_task_specs() if spec.queue == "crm"}
    brokers = registered_queue_brokers()
    crm_broker = brokers["crm"]

    for task_name in CRM_SCHEDULER_TASK_NAMES:
        assert task_name in scheduled_names
        assert crm_broker.find_task(task_name) is not None


def test_crm_scheduled_tasks_accept_scheduler_payload() -> None:
    suggest_sig = _task_signature(crm_generate_namespace_suggests_tick)
    reconcile_sig = _task_signature(reconcile_daily_summary_task)
    reembed_sig = _task_signature(crm_reembed_stale_documents_tick)
    integration_sig = _task_signature(scheduled_namespace_integration_unified_sync)

    assert "schedule_task_id" in suggest_sig.parameters
    assert "schedule_task_id" in reconcile_sig.parameters
    assert "company_id" in reconcile_sig.parameters
    assert "schedule_task_id" in reembed_sig.parameters
    assert "company_id" in reembed_sig.parameters
    assert "schedule_task_id" in integration_sig.parameters


def test_crm_queue_is_in_platform_wiring() -> None:
    assert "crm" in all_queues()

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import cast

from apps.crm.scheduled_integration_constants import (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
)
from apps.crm.scheduled_task_constants import (
    CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
    CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME,
    CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
)
from apps.crm_worker.tasks.daily_summary_tasks import reconcile_daily_summary_task
from apps.crm_worker.tasks.reembed_tasks import crm_reembed_stale_documents_tick
from apps.crm_worker.tasks.scheduled_integration_sync_tasks import (
    scheduled_namespace_integration_unified_sync,
)
from apps.crm_worker.tasks.suggest_tasks import crm_generate_namespace_suggests_tick

CRM_SCHEDULER_TASK_NAMES = (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
    CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
    CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
    CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME,
)


def _task_signature(task: object) -> inspect.Signature:
    wrapped = cast(Callable[..., object], task)
    unwrapped = cast(Callable[..., object], inspect.unwrap(wrapped))
    return inspect.signature(unwrapped)


def test_crm_scheduler_tasks_are_registered_for_scheduler() -> None:
    import apps.scheduler.scheduler as scheduler_module

    assert scheduler_module.scheduler is not None
    required_names = scheduler_module._CRM_SCHEDULER_REQUIRED_TASK_NAMES  # pyright: ignore[reportPrivateUsage]
    for task_name in CRM_SCHEDULER_TASK_NAMES:
        assert task_name in required_names


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


def test_crm_worker_entrypoint_imports_scheduler_task_modules() -> None:
    import apps.crm_worker.worker as worker_module

    source = Path(worker_module.__file__).read_text()
    assert "apps.crm_worker.tasks.scheduled_integration_sync_tasks" in source
    assert "apps.crm_worker.tasks.reembed_tasks" in source
    assert "apps.crm_worker.tasks.suggest_tasks" in source
    assert "apps.crm_worker.tasks.daily_summary_tasks" in source

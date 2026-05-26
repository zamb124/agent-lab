"""TaskIQ broker для flows worker."""

# ruff: noqa: E402

import os
import sys

from apps.flows_worker.broker_core import broker, recovery_handler, scheduler
from core.logging import get_logger

logger = get_logger(__name__)

import apps.flows_worker.evaluation_tasks as _evaluation_tasks

logger.info(
    "worker.broker_task_registry",
    tasks=sorted(broker.local_task_registry.keys()),
)


def _should_register_tasks() -> bool:
    if os.environ.get("FLOWS_WORKER_REGISTER_TASKS") == "true":
        return True
    argv = " ".join(sys.argv)
    return "taskiq" in argv and "apps.flows_worker.worker:worker_app" in argv


if _should_register_tasks():
    # TaskIQ starts receivers from the broker module before worker startup hooks.
    # Keep task registration attached to the worker broker itself, while producer
    # processes can import this broker without pulling runtime task modules.
    import apps.flows.src.tasks.company_init_tasks as _company_init_tasks
    import apps.flows.src.tasks.flow_tasks as _flow_tasks
    import apps.flows.src.tasks.llm_tasks as _llm_tasks
    import apps.flows.src.tasks.node_tasks as _node_tasks
    import apps.flows.src.tasks.scheduled_tasks as _scheduled_tasks
    import apps.flows.src.tasks.tool_tasks as _tool_tasks

    _TASK_REGISTRATION_MODULES = (
        _company_init_tasks,
        _flow_tasks,
        _llm_tasks,
        _node_tasks,
        _scheduled_tasks,
        _tool_tasks,
    )
    logger.info(
        "worker.full_task_registry",
        tasks=sorted(broker.local_task_registry.keys()),
    )

_EVALUATION_TASK_REGISTRATION_MODULES = (_evaluation_tasks,)

__all__ = ["broker", "scheduler", "recovery_handler"]

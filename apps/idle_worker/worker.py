"""
Точка входа для Idle Worker (очередь ``idle``).

Запуск: taskiq worker apps.idle_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

import importlib
from apps.flows.config import FlowSettings
from apps.flows.config import set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_idle_worker_flow_settings = FlowSettings.model_validate(_merged_flows)
setup_worker_logging_early("idle_worker", logging_config=_idle_worker_flow_settings.logging)
set_flow_settings(_idle_worker_flow_settings)

from taskiq import TaskiqState

from apps.idle_worker.container import get_container
from apps.idle_worker.tasks.task_names import (
    TASK_INIT_SYSTEM_COMPANY,
    TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK,
)
from apps.platform_tasks.wiring import wire_worker

from core.clients.llm.mock import configure_mock_llm_redis, get_or_create_global_mock_llm
from core.config.testing import is_testing
from core.logging import get_logger
from core.tasks import enqueue
from core.tasks.worker_bootstrap import (
    build_worker,
    connect_redis_with_backoff,
    init_worker_tracing,
)

# side-effect: register platform event catalog types
_ = importlib.import_module("core.calendar.events")
_ = importlib.import_module("core.mail.events")

logger = get_logger(__name__)

broker = wire_worker("idle")


async def _startup(state: TaskiqState) -> None:
    container = get_container()
    state.container = container

    await connect_redis_with_backoff(container.redis_client, service_name="idle_worker")
    init_worker_tracing("idle_worker", container)

    if is_testing():
        _ = get_or_create_global_mock_llm("mock-gpt-4")
        _ = configure_mock_llm_redis(container.redis_client)
        logger.info("worker.mock_llm_configured", service="idle_worker")
    else:
        system_init_task = await enqueue(TASK_INIT_SYSTEM_COMPANY, background_kind="startup")
        logger.info(
            "company_init.system_enqueued",
            service="idle_worker",
            task_id=system_init_task.task_id,
        )
        tag_groups_task = await enqueue(
            TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK, background_kind="startup"
        )
        logger.info(
            "tool_tag_groups.describe_enqueued",
            service="idle_worker",
            task_id=tag_groups_task.task_id,
        )

    logger.info("worker.container_initialized", service="idle_worker")


async def _shutdown(state: TaskiqState) -> None:
    _ = state
    container = get_container()
    try:
        await container.redis_client.close()
        logger.info("worker.redis_disconnected", service="idle_worker")
    except Exception as exc:
        logger.exception(
            "worker.redis_close_failed",
            service="idle_worker",
            **{"exception.type": type(exc).__name__},
        )
    logger.info("worker.container_closed", service="idle_worker")


worker_app = build_worker(
    broker,
    service_name="idle_worker",
    queue="idle",
    on_startup=_startup,
    on_shutdown=_shutdown,
)

__all__ = ["worker_app"]

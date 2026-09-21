"""
Точка входа для Idle Worker (очередь ``idle``).

Запуск: taskiq worker apps.idle_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

import importlib
from core.config import BaseSettings, set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_idle_worker_settings = BaseSettings.model_validate(load_merged_config(service_name="idle_worker", silent=True))
setup_worker_logging_early("idle_worker", logging_config=_idle_worker_settings.logging)
set_settings(_idle_worker_settings)
_segment = resolve_files_route_segment("idle_worker")
set_files_route_segment(_segment)

from taskiq import TaskiqState

from apps.idle_worker.container import get_container
from apps.idle_worker.tasks.task_names import TASK_INIT_SYSTEM_COMPANY
from apps.platform_tasks.wiring import wire_worker

from core.config.testing import is_testing
from core.logging import get_logger
from core.tasks import enqueue
from core.tasks.worker_bootstrap import (
    build_worker,
    connect_redis_with_backoff,
    init_worker_testing_mock_llm,
    init_worker_tracing,
)

# side-effect: register platform event catalog types
_ = importlib.import_module("core.calendar.events")
_ = importlib.import_module("core.mail.events")

logger = get_logger(__name__)

broker = wire_worker("idle")


async def _startup(state: TaskiqState) -> None:
    container = get_container()
    container.bind_files_route_segment(_segment)
    state.container = container

    await connect_redis_with_backoff(container.redis_client, service_name="idle_worker")
    init_worker_tracing("idle_worker", container)

    if is_testing():
        init_worker_testing_mock_llm(container.redis_client, service_name="idle_worker")
    else:
        system_init_task = await enqueue(TASK_INIT_SYSTEM_COMPANY, background_kind="startup")
        logger.info(
            "company_init.system_enqueued",
            service="idle_worker",
            task_id=system_init_task.task_id,
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

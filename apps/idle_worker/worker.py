"""
Точка входа для Idle Worker (очередь ``idle``).

Запуск: taskiq worker apps.idle_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from core.config import BaseSettings, set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_idle_worker_settings = BaseSettings.model_validate(
    load_merged_config(service_name="idle_worker", silent=True)
)
setup_worker_logging_early("idle_worker", logging_config=_idle_worker_settings.logging)
set_settings(_idle_worker_settings)
set_files_route_segment(resolve_files_route_segment("idle_worker"))

from apps.idle_worker.di import IdleWorkerDi
from apps.idle_worker.tasks.task_names import TASK_INIT_SYSTEM_COMPANY
from apps.worker_manifest import wire_worker
from core.clients.redis_client import RedisClient
from core.config.testing import is_testing
from core.di import recipe
from core.logging import get_logger
from core.tasks import enqueue
from core.tasks.worker_bootstrap import build_worker, connect_redis_with_backoff

logger = get_logger(__name__)


async def connect_idle_worker_redis(redis_client: RedisClient) -> None:
    await connect_redis_with_backoff(redis_client, service_name="idle_worker")


async def enqueue_system_company_init() -> None:
    if is_testing():
        return
    system_init_task = await enqueue(TASK_INIT_SYSTEM_COMPANY, background_kind="startup")
    logger.info(
        "company_init.system_enqueued",
        service="idle_worker",
        task_id=system_init_task.task_id,
    )


broker = wire_worker("idle")
worker_app = build_worker(
    broker,
    service_name="idle_worker",
    queue="idle",
    settings=_idle_worker_settings,
    di_class=IdleWorkerDi,
    database="shared_url",
    lifecycle=(recipe(connect_idle_worker_redis), recipe(enqueue_system_company_init)),
)

__all__ = ["worker_app"]

"""
Воркер доставки A2A push (очередь ``a2a_push``).

Отдельный процесс от idle: IMAP ``mail_sync_tick`` не держит webhook.
Запуск: taskiq worker apps.idle.worker_a2a_push:worker_app
"""

# ruff: noqa: E402, I001

from core.config import BaseSettings, set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = BaseSettings.model_validate(load_merged_config(service_name="idle_worker", silent=True))
setup_worker_logging_early("a2a_push_worker", logging_config=_settings.logging)
set_settings(_settings)
set_files_route_segment(resolve_files_route_segment("idle_worker"))

from apps.idle.di import IdleDi
from apps.worker_manifest import wire_worker
from core.clients.redis_client import RedisClient
from core.di import recipe
from core.tasks.worker_bootstrap import build_worker, connect_redis_with_backoff


async def connect_a2a_push_redis(redis_client: RedisClient) -> None:
    await connect_redis_with_backoff(redis_client, service_name="a2a_push_worker")


broker = wire_worker("a2a_push")
worker_app = build_worker(
    broker,
    service_name="a2a_push_worker",
    queue="a2a_push",
    settings=_settings,
    di_class=IdleDi,
    database="shared_url",
    lifecycle=(recipe(connect_a2a_push_redis),),
)

__all__ = ["worker_app"]

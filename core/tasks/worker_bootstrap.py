"""Единый lifecycle TaskIQ-воркера.

``build_worker`` инкапсулирует то, что раньше копипастилось в каждом
``apps/<svc>_worker/worker.py``: регистрацию startup/shutdown событий и recovery
зависших задач. Доменная инициализация (billing, redis, file processors,
notification_manager, tracing) — явными типизированными вызовами хелперов внутри
``on_startup`` конкретного воркера.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

from taskiq import TaskiqState
from taskiq_redis import RedisStreamBroker

from core.config import get_settings
from core.events import store_registered_platform_events
from core.logging import get_logger
from core.tasks.broker import create_stale_tasks_recovery, register_worker_events
from core.tracing import setup_tracing
from core.tracing.repository import SpanRepository
from core.tracing.tracer import set_span_repository, set_tracing_service_name

logger = get_logger(__name__)

WorkerHook = Callable[[TaskiqState], Awaitable[None]]


class _SpanRepoContainer(Protocol):
    @property
    def span_repository(self) -> SpanRepository: ...


class _RedisConnectClient(Protocol):
    async def connect(self) -> None: ...


def init_worker_tracing(service_name: str, container: object) -> None:
    """Единый tracing-блок воркера (был байт-в-байт скопирован в 5 воркерах)."""
    settings = get_settings()
    if not settings.tracing.enabled:
        return
    setup_tracing(settings.tracing)
    if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
        if not settings.database.tracing_url:
            raise ValueError(
                "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
            )
        set_tracing_service_name(service_name)
        set_span_repository(cast(_SpanRepoContainer, container).span_repository)
    logger.info("worker.tracing_initialized", service=service_name)


async def connect_redis_with_backoff(
    redis_client: _RedisConnectClient,
    *,
    service_name: str,
) -> None:
    """Подключение к Redis с ретраями (был скопирован в flows/idle воркерах)."""
    logger.info("worker.redis_connecting", service=service_name)
    retry_delays: tuple[int, ...] = (1, 2, 4, 8)
    max_retries = len(retry_delays) + 1
    for attempt in range(max_retries):
        try:
            await redis_client.connect()
            logger.info("worker.redis_connected", service=service_name)
            return
        except Exception:
            if attempt >= max_retries - 1:
                logger.error("worker.redis_connect_failed", service=service_name)
                raise
            wait_seconds = retry_delays[attempt]
            logger.warning(
                "worker.redis_connect_retry",
                service=service_name,
                attempt=attempt + 1,
                wait_seconds=wait_seconds,
            )
            await asyncio.sleep(wait_seconds)


def build_worker(
    broker: RedisStreamBroker,
    *,
    service_name: str,
    queue: str,
    on_startup: WorkerHook | None = None,
    on_shutdown: WorkerHook | None = None,
) -> RedisStreamBroker:
    """Зарегистрировать единый lifecycle воркера и вернуть broker (worker_app).

    Startup: recovery зависших задач → доменный ``on_startup``.
    Shutdown: доменный ``on_shutdown``.
    """
    recovery_handler = create_stale_tasks_recovery(queue_name=queue)

    async def _startup(state: TaskiqState) -> None:
        await recovery_handler()
        if on_startup is not None:
            await on_startup(state)
        await store_registered_platform_events()
        logger.info("worker.started", service=service_name, queue=queue)

    async def _shutdown(state: TaskiqState) -> None:
        if on_shutdown is not None:
            await on_shutdown(state)
        logger.info("worker.stopped", service=service_name, queue=queue)

    register_worker_events(broker, _startup, _shutdown, service_name=service_name)
    return broker


__all__ = [
    "WorkerHook",
    "build_worker",
    "connect_redis_with_backoff",
    "init_worker_tracing",
]

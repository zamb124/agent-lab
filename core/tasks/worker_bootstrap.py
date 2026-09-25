"""Единый lifecycle TaskIQ-воркера на Service Kit.

``build_worker`` — единственный вход worker-процесса: recovery зависших задач, tracing,
file processors, eager-сборка ``<Svc>Di`` через ``open_di`` в ``TaskiqState.di`` и
закрытие на shutdown. Процессные действия воркера — ``lifecycle`` recipes.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Protocol

from taskiq import TaskiqState
from taskiq_redis import RedisStreamBroker

from core.billing import set_billing_service
from core.clients.llm.mock import configure_mock_llm_redis, get_or_create_global_mock_llm
from core.clients.redis_client import RedisClient
from core.config import BaseSettings, get_settings
from core.config.testing import is_testing
from core.di.kit import ProcessIdentity, Recipe, ServiceDi
from core.di.platform import PlatformDi
from core.di.process import open_di
from core.di.state import clear_task_di, set_task_di
from core.events import store_registered_platform_events
from core.files.processors import initialize_default_processors
from core.files.urls import resolve_files_route_segment
from core.logging import get_logger
from core.tasks.broker import create_stale_tasks_recovery, register_worker_events
from core.tracing import setup_tracing
from core.types import MigrationDatabaseUrlKey

logger = get_logger(__name__)


class _RedisConnectClient(Protocol):
    async def connect(self) -> None: ...


def init_worker_tracing(service_name: str) -> None:
    """Единый tracing-блок воркера (был байт-в-байт скопирован в 5 воркерах)."""
    settings = get_settings()
    if not settings.tracing.enabled:
        return
    setup_tracing(settings.tracing)
    logger.info("worker.tracing_initialized", service=service_name)


def init_worker_testing_mock_llm(redis_client: RedisClient, *, service_name: str) -> None:
    """В TESTING подключает process-local MockLLM к Redis-очереди ``test_scope``."""
    if not is_testing():
        return
    _ = get_or_create_global_mock_llm("mock-gpt-4")
    mock_llm = configure_mock_llm_redis(redis_client)
    if mock_llm is None:
        raise RuntimeError(f"{service_name}: MockLLM is not registered for Redis")
    logger.info("worker.mock_llm_configured", service=service_name)


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
    settings: BaseSettings,
    di_class: type[ServiceDi],
    database: MigrationDatabaseUrlKey,
    lifecycle: tuple[Recipe, ...] = (),
) -> RedisStreamBroker:
    """Зарегистрировать lifecycle воркера и вернуть broker (worker_app).

    Startup: recovery → tracing → file processors → ``open_di`` в ``TaskiqState.di``
    (включая ``lifecycle``) → каталог событий. Shutdown закрывает DI в обратном порядке.
    """
    recovery_handler = create_stale_tasks_recovery(queue_name=queue)
    identity = ProcessIdentity(
        service_name=service_name,
        files_route_segment=resolve_files_route_segment(service_name),
    )
    stack = AsyncExitStack()

    async def _startup(state: TaskiqState) -> None:
        await recovery_handler()
        init_worker_tracing(service_name)
        initialize_default_processors()
        di = await stack.enter_async_context(
            open_di(di_class, settings=settings, identity=identity, database=database, lifecycle=lifecycle)
        )
        if isinstance(di, PlatformDi):
            set_billing_service(di.billing_service)
            init_worker_testing_mock_llm(di.redis_client, service_name=service_name)
        set_task_di(state, di)
        await store_registered_platform_events()
        logger.info("worker.started", service=service_name, queue=queue)

    async def _shutdown(state: TaskiqState) -> None:
        clear_task_di(state)
        await stack.aclose()
        logger.info("worker.stopped", service=service_name, queue=queue)

    register_worker_events(broker, _startup, _shutdown, service_name=service_name)
    return broker


__all__ = [
    "build_worker",
    "connect_redis_with_backoff",
    "init_worker_testing_mock_llm",
    "init_worker_tracing",
]

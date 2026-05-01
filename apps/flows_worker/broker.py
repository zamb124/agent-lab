"""
Flows worker для задач сервиса flows.

Использует очереди:
- "default" для основных задач flows
- "scheduled" для планировщика flows
"""

import asyncio
import os

from core.config.testing import is_testing

from taskiq import TaskiqState

from core.billing import set_billing_service
from core.logging import get_logger
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)

logger = get_logger(__name__)

# Создаем broker для задач flows с очередью "flows_worker"
broker = create_broker(queue_name="flows_worker", service_name="flows_worker")
scheduler = create_scheduler(broker)

# Регистрируем recovery зависших задач для очереди "flows_worker"
recovery_handler = create_stale_tasks_recovery(queue_name="flows_worker")
broker.on_event("startup")(recovery_handler)

async def _initialize_worker_state(state: TaskiqState, service_name: str) -> None:
    """Инициализация контейнера при старте worker."""
    from apps.flows.config import get_settings
    from apps.flows.src.container import get_container
    from core.config import set_settings as set_core_settings
    from core.tracing import setup_tracing
    from core.tracing.tracer import set_span_repository, set_tracing_service_name

    settings = get_settings()
    set_core_settings(settings)

    container = get_container()
    state.container = container

    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service=service_name)

    # Курс USD/RUB от ЦБ РФ: один запрос при старте, затем фоновое обновление.
    from core.billing.cbr_rate_provider import refresh_rate_once as _cbr_refresh_once
    from core.billing.cbr_rate_provider import refresh_loop_coro as _cbr_loop_coro
    from core.utils.background import run_with_log_context

    _cbr_fallback = settings.billing.usd_to_rub_rate
    await _cbr_refresh_once(fallback=_cbr_fallback)
    run_with_log_context(
        _cbr_loop_coro(fallback=_cbr_fallback),
        name="billing.cbr_rate_refresh",
        background_kind="startup",
    )
    logger.info("worker.cbr_rate_initialized", service=service_name)

    from core.files.processors import initialize_default_processors
    from core.files.writer import FileWriter

    initialize_default_processors(container.file_repository)

    s = get_settings()
    FileWriter.configure_process_upload(
        file_processor=container.file_processor,
        download_url_prefix=f"/{s.server.name}/api/v1/files/download",
    )

    # Внутри воркера выполняем ноды напрямую, без рекурсивного kiq().
    container.use_worker = False

    logger.info("worker.redis_connecting", service=service_name)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("worker.redis_connected", service=service_name)
            break
        except Exception:
            if attempt < max_retries - 1:
                wait_seconds = 2**attempt
                logger.warning(
                    "worker.redis_connect_retry",
                    service=service_name,
                    attempt=attempt + 1,
                    wait_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error("worker.redis_connect_failed", service=service_name)
                raise

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("flows_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service=service_name)

    if is_testing():
        from core.clients.llm.factory import get_llm
        from core.clients.llm.mock import configure_mock_llm_redis

        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("worker.mock_llm_configured", service=service_name)

    logger.info("worker.container_initialized", service=service_name)


async def worker_startup(state: TaskiqState) -> None:
    """Инициализация контейнера при старте platform worker."""
    await _initialize_worker_state(state=state, service_name="flows_worker")


async def worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке worker."""
    if hasattr(state, "container"):
        try:
            await state.container.redis_client.close()
            logger.info("worker.redis_disconnected")
        except Exception as exc:
            logger.exception(
                "worker.redis_close_failed",
                **{"exception.type": type(exc).__name__},
            )
    logger.info("worker.container_closed")


register_worker_events(
    broker,
    worker_startup,
    worker_shutdown,
    service_name="flows_worker",
)

logger.info("worker.broker_created", queue="flows_worker")

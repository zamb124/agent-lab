"""
Idle worker для фоновых периодических задач.

Использует очередь:
- "idle" для длительных/регулярных фоновых задач
"""

import asyncio

from taskiq import TaskiqState

from core.config.testing import is_testing
from core.logging import get_logger
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)

logger = get_logger(__name__)

broker = create_broker(queue_name="idle", service_name="idle_worker")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="idle")
broker.on_event("startup")(recovery_handler)


async def idle_worker_startup(state: TaskiqState) -> None:
    """Инициализация контейнера при старте idle worker."""
    from apps.flows.config import get_settings
    from apps.flows.src.container import get_container
    from core.tracing import setup_tracing
    from core.tracing.tracer import set_span_repository, set_tracing_service_name

    settings = get_settings()

    container = get_container()
    state.container = container
    container.use_worker = False

    logger.info("worker.redis_connecting", service="idle_worker")
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("worker.redis_connected", service="idle_worker")
            break
        except Exception:
            if attempt < max_retries - 1:
                wait_seconds = 2**attempt
                logger.warning(
                    "worker.redis_connect_retry",
                    service="idle_worker",
                    attempt=attempt + 1,
                    wait_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error("worker.redis_connect_failed", service="idle_worker")
                raise

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("idle_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service="idle_worker")

    if is_testing():
        from core.clients.llm.factory import get_llm
        from core.clients.llm.mock import configure_mock_llm_redis

        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("worker.mock_llm_configured", service="idle_worker")

    logger.info("worker.container_initialized", service="idle_worker")


async def idle_worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке idle worker."""
    if hasattr(state, "container"):
        try:
            await state.container.redis_client.close()
            logger.info("worker.redis_disconnected", service="idle_worker")
        except Exception as exc:
            logger.exception(
                "worker.redis_close_failed",
                service="idle_worker",
                **{"exception.type": type(exc).__name__},
            )
    logger.info("worker.container_closed", service="idle_worker")


register_worker_events(
    broker,
    idle_worker_startup,
    idle_worker_shutdown,
    service_name="idle_worker",
)

logger.info("worker.broker_created", queue="idle")

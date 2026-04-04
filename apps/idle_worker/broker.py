"""
Idle worker для фоновых периодических задач.

Использует очередь:
- "idle" для длительных/регулярных фоновых задач
"""

import asyncio
import os

from taskiq import TaskiqState

from core.logging import get_logger, setup_logging
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)

logger = get_logger(__name__)

broker = create_broker(queue_name="idle")
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
    setup_logging(service_name="idle_worker")

    container = get_container()
    state.container = container
    container.use_worker = False

    logger.info("Idle worker: connecting to Redis...")
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("Idle worker: Redis connected")
            break
        except Exception:
            if attempt < max_retries - 1:
                wait_seconds = 2**attempt
                logger.warning(
                    "Idle worker: Redis connection attempt %s failed, retry in %ss",
                    attempt + 1,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error("Idle worker: Failed to connect to Redis")
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
        logger.info("Idle worker: трейсинг инициализирован")

    if os.environ.get("TESTING") == "true":
        from core.clients.llm.factory import get_llm
        from core.clients.llm.mock import configure_mock_llm_redis

        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("Idle worker: MockLLM настроен для чтения из Redis")

    logger.info("Idle worker: контейнер инициализирован")


async def idle_worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке idle worker."""
    if hasattr(state, "container"):
        try:
            await state.container.redis_client.close()
            logger.info("Idle worker: Redis disconnected")
        except Exception as error:
            logger.error(f"Idle worker: Error closing Redis: {error}")
    logger.info("Idle worker: контейнер закрыт")


register_worker_events(broker, idle_worker_startup, idle_worker_shutdown)

logger.info("✅ Idle worker broker создан (queue='idle')")

"""
Flows worker для задач сервиса flows.

Использует очереди:
- "default" для основных задач flows
- "scheduled" для планировщика flows
"""

import asyncio
import os

from taskiq import TaskiqState

from core.billing import set_billing_service
from core.logging import get_logger, setup_logging
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)

logger = get_logger(__name__)

# Создаем broker для задач flows с очередью "flows_worker"
broker = create_broker(queue_name="flows_worker")
scheduler = create_scheduler(broker)

# Регистрируем recovery зависших задач для очереди "flows_worker"
recovery_handler = create_stale_tasks_recovery(queue_name="flows_worker")
broker.on_event("startup")(recovery_handler)

async def _initialize_worker_state(state: TaskiqState, service_name: str) -> None:
    """Инициализация контейнера при старте worker."""
    from apps.flows.config import get_settings
    from apps.flows.src.container import get_container
    from core.tracing import setup_tracing
    from core.tracing.tracer import set_span_repository, set_tracing_service_name

    settings = get_settings()
    setup_logging(service_name=service_name)

    container = get_container()
    state.container = container

    set_billing_service(container.billing_service)
    logger.info("Worker: BillingService инициализирован")

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

    logger.info("Worker: connecting to Redis...")
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("Worker: Redis connected")
            break
        except Exception:
            if attempt < max_retries - 1:
                wait_seconds = 2**attempt
                logger.warning(
                    f"Worker: Redis connection attempt {attempt + 1} failed, retry in {wait_seconds}s"
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error("Worker: Failed to connect to Redis")
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
        logger.info("Worker: трейсинг инициализирован")

    if os.environ.get("TESTING") == "true":
        from core.clients.llm.factory import get_llm
        from core.clients.llm.mock import configure_mock_llm_redis

        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("Worker: MockLLM настроен для чтения из Redis")

    logger.info("Worker: контейнер инициализирован")


async def worker_startup(state: TaskiqState) -> None:
    """Инициализация контейнера при старте platform worker."""
    await _initialize_worker_state(state=state, service_name="flows_worker")


async def worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке worker."""
    if hasattr(state, "container"):
        try:
            await state.container.redis_client.close()
            logger.info("Worker: Redis disconnected")
        except Exception as error:
            logger.error(f"Worker: Error closing Redis: {error}")
    logger.info("Worker: контейнер закрыт")


register_worker_events(broker, worker_startup, worker_shutdown)

logger.info("✅ Flows worker broker создан (queue='flows_worker')")

"""
Platform broker для задач agents, crm и других сервисов.

Использует очередь "default" (где регистрируются все задачи platform).
"""

import asyncio
import os
from taskiq import TaskiqState

from core.tasks.broker import (
    create_broker, 
    create_scheduler, 
    create_stale_tasks_recovery,
    register_worker_events
)
from core.logging import get_logger, setup_logging

logger = get_logger(__name__)

# Создаем broker для платформенных задач с очередью "default"
broker = create_broker(queue_name="default")
scheduler = create_scheduler(broker)

# Регистрируем recovery зависших задач для очереди "default"
recovery_handler = create_stale_tasks_recovery(queue_name="default")
broker.on_event("startup")(recovery_handler)


# Обработчики запуска и остановки воркера
async def worker_startup(state: TaskiqState) -> None:
    """Инициализация контейнера при старте worker."""
    from apps.flows.config import get_settings
    from apps.flows.src.container import get_container
    from core.tracing import setup_tracing
    from core.tracing.tracer import set_span_repository

    settings = get_settings()
    setup_logging(service_name="platform-worker")

    container = get_container()
    state.container = container
    
    # Внутри воркера выполняем ноды напрямую, без рекурсивного kiq()
    container.use_worker = False
    
    logger.info("Worker: connecting to Redis...")
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("Worker: Redis connected")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Worker: Redis connection attempt {attempt+1} failed, retry in {wait}s")
                await asyncio.sleep(wait)
            else:
                logger.error("Worker: Failed to connect to Redis")
                raise

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, 'span_repository'):
            set_span_repository(container.span_repository)
        logger.info("Worker: трейсинг инициализирован")

    if os.environ.get("TESTING") == "true":
        from core.clients.llm.mock import configure_mock_llm_redis
        from core.clients.llm.factory import get_llm
        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("Worker: MockLLM настроен для чтения из Redis")

    logger.info("Worker: контейнер инициализирован")


async def worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке worker."""
    if hasattr(state, 'container'):
        try:
            await state.container.redis_client.close()
            logger.info("Worker: Redis disconnected")
        except Exception as e:
            logger.error(f"Worker: Error closing Redis: {e}")
    logger.info("Worker: контейнер закрыт")


# Регистрируем worker events
register_worker_events(broker, worker_startup, worker_shutdown)

logger.info("✅ Platform broker создан (queue='taskiq')")

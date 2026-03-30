"""
RAG Worker broker для RAG задач.

Использует очередь "rag" для изоляции от платформенных задач.
"""

from taskiq import TaskiqState

from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)
from core.logging import get_logger, setup_logging

logger = get_logger(__name__)

broker = create_broker(queue_name="rag")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="rag")
broker.on_event("startup")(recovery_handler)


async def rag_worker_startup(state: TaskiqState) -> None:
    """Инициализация RAG Worker при старте."""
    from apps.rag_worker.config import get_settings
    from core.rag.factory import get_default_rag_provider

    setup_logging(service_name="rag_worker")

    settings = get_settings()
    provider = get_default_rag_provider()
    state.rag_provider = provider

    logger.info("RAG Worker: RAG provider инициализирован")
    logger.info(f"RAG Worker: используется провайдер {settings.rag.default_provider}")


async def rag_worker_shutdown(state: TaskiqState) -> None:
    """Остановка RAG Worker."""
    logger.info("RAG Worker: остановка")


register_worker_events(broker, rag_worker_startup, rag_worker_shutdown)

logger.info("RAG Worker broker создан (queue='rag')")

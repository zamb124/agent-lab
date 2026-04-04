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
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name

logger = get_logger(__name__)

broker = create_broker(queue_name="rag")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="rag")
broker.on_event("startup")(recovery_handler)


async def rag_worker_startup(state: TaskiqState) -> None:
    """Инициализация RAG Worker при старте."""
    from apps.rag.container import get_rag_container
    from apps.rag_worker.config import get_settings
    from core.rag.factory import get_default_rag_provider

    setup_logging(service_name="rag_worker")

    settings = get_settings()
    container = get_rag_container()
    state.container = container
    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("rag_worker")
            set_span_repository(container.span_repository)
        logger.info("RAG Worker: трейсинг инициализирован")
    provider = get_default_rag_provider()
    state.rag_provider = provider

    logger.info("RAG Worker: RAG provider инициализирован")
    logger.info(f"RAG Worker: используется провайдер {settings.rag.default_provider}")


async def rag_worker_shutdown(state: TaskiqState) -> None:
    """Остановка RAG Worker."""
    logger.info("RAG Worker: остановка")


register_worker_events(broker, rag_worker_startup, rag_worker_shutdown)

logger.info("RAG Worker broker создан (queue='rag')")

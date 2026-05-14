"""
RAG Worker broker для RAG задач.

Использует очередь "rag" для изоляции от платформенных задач.
"""

from taskiq import TaskiqState

from core.billing import set_billing_service
from core.logging import get_logger
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name

logger = get_logger(__name__)

broker = create_broker(queue_name="rag", service_name="rag_worker")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="rag")
broker.on_event("startup")(recovery_handler)


async def rag_worker_startup(state: TaskiqState) -> None:
    """Инициализация RAG Worker при старте."""
    from apps.rag.container import get_rag_container
    from apps.rag_worker.config import get_settings
    from core.config import set_settings

    settings = get_settings()
    container = get_rag_container()
    state.container = container

    from core.files.processors import initialize_default_processors

    initialize_default_processors(container.file_repository)
    set_settings(settings)
    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service="rag_worker")

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("rag_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service="rag_worker")
    provider = container.rag_provider
    state.rag_provider = provider

    logger.info(
        "worker.rag_provider_initialized",
        service="rag_worker",
        provider=settings.rag.default_provider,
    )


async def rag_worker_shutdown(state: TaskiqState) -> None:
    """Остановка RAG Worker."""
    logger.info("worker.stopping", service="rag_worker")


register_worker_events(
    broker,
    rag_worker_startup,
    rag_worker_shutdown,
    service_name="rag_worker",
)

logger.info("worker.broker_created", queue="rag")

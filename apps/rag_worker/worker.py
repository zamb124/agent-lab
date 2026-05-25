"""
RAG Worker startup/shutdown события и регистрация tasks.
"""

# ruff: noqa: E402, I001

from apps.rag_worker.config import RAGWorkerSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_rag_worker = load_merged_config(service_name="rag_worker", silent=True)
_rag_worker_settings = RAGWorkerSettings.model_validate(_merged_rag_worker)
setup_worker_logging_early("rag_worker", logging_config=_rag_worker_settings.logging)
set_settings(_rag_worker_settings)

from taskiq import TaskiqState  # noqa: E402

from apps.rag.container import get_rag_container  # noqa: E402
from apps.rag_worker.broker import broker as worker_app, recovery_handler  # noqa: E402
from apps.rag_worker.config import get_settings  # noqa: E402
from core.billing import set_billing_service  # noqa: E402
from core.files.processors import initialize_default_processors  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.tasks.broker import register_worker_events  # noqa: E402
from core.tracing import setup_tracing  # noqa: E402
from core.tracing.tracer import set_span_repository, set_tracing_service_name  # noqa: E402

logger = get_logger(__name__)


async def rag_worker_startup(state: TaskiqState) -> None:
    """Инициализация RAG Worker при старте."""
    settings = get_settings()
    container = get_rag_container()
    state.container = container

    await recovery_handler()

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
    _ = state
    logger.info("worker.stopping", service="rag_worker")


register_worker_events(
    worker_app,
    rag_worker_startup,
    rag_worker_shutdown,
    service_name="rag_worker",
)

# Импорт всех задач для регистрации в worker app
import apps.rag_worker.tasks.indexing_tasks as _indexing_tasks  # noqa: E402
import apps.rag_worker.tasks.maintenance_tasks as _maintenance_tasks  # noqa: E402

_TASK_REGISTRATION_MODULES = (
    _indexing_tasks,
    _maintenance_tasks,
)

__all__ = ["worker_app"]

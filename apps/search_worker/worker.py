"""Search worker startup and task registration."""

# ruff: noqa: E402, I001

from apps.search_worker.config import SearchWorkerSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_search_worker = load_merged_config(service_name="search_worker", silent=True)
_search_worker_settings = SearchWorkerSettings.model_validate(_merged_search_worker)
setup_worker_logging_early("search_worker", logging_config=_search_worker_settings.logging)
set_settings(_search_worker_settings)

from taskiq import TaskiqState  # noqa: E402

from apps.search.container import get_search_container  # noqa: E402
from apps.search_worker.broker import broker as worker_app, recovery_handler  # noqa: E402
from apps.search_worker.config import get_settings  # noqa: E402
from core.billing import set_billing_service  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.tasks.broker import register_worker_events  # noqa: E402
from core.tracing import setup_tracing  # noqa: E402
from core.tracing.tracer import set_span_repository, set_tracing_service_name  # noqa: E402

logger = get_logger(__name__)


async def search_worker_startup(state: TaskiqState) -> None:
    settings = get_settings()
    container = get_search_container()
    state.container = container

    await recovery_handler()

    set_settings(settings)
    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service="search_worker")

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled requires database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("search_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service="search_worker")

    bootstrap_result = await container.crawl_bootstrap_service.ensure_crawl_pipeline_ready()
    logger.info(
        "worker.crawl_bootstrap",
        service="search_worker",
        crawl_profile_id=bootstrap_result.crawl_profile_id,
        action=bootstrap_result.action,
        domain_count=bootstrap_result.domain_count,
    )


async def search_worker_shutdown(state: TaskiqState) -> None:
    _ = state
    logger.info("worker.stopping", service="search_worker")


register_worker_events(
    worker_app,
    search_worker_startup,
    search_worker_shutdown,
    service_name="search_worker",
)

import apps.search_worker.tasks.crawl_tasks as _search_crawl_tasks  # noqa: E402

_TASK_REGISTRATION_MODULES = (_search_crawl_tasks,)

__all__ = ["worker_app"]

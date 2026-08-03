"""Search Worker (очередь ``search``).

Запуск: taskiq worker apps.search_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.search_worker.config import SearchWorkerSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = SearchWorkerSettings.model_validate(
    load_merged_config(service_name="search_worker", silent=True)
)
setup_worker_logging_early("search_worker", logging_config=_settings.logging)
set_settings(_settings)
_segment = resolve_files_route_segment("search_worker")
set_files_route_segment(_segment)

from taskiq import TaskiqState

from apps.platform_tasks.wiring import wire_worker
from apps.search.container import get_search_container
from core.billing import set_billing_service
from core.crawl.logging_events import log_crawl_bootstrap
from core.logging import get_logger
from core.tasks.worker_bootstrap import build_worker, init_worker_tracing

logger = get_logger(__name__)

broker = wire_worker("search")


async def _startup(state: TaskiqState) -> None:
    container = get_search_container()
    container.bind_files_route_segment(_segment)
    state.container = container
    set_billing_service(container.billing_service)
    init_worker_tracing("search_worker", container)

    bootstrap_result = await container.crawl_bootstrap_service.ensure_crawl_pipeline_ready()
    log_crawl_bootstrap(
        crawl_profile_id=bootstrap_result.crawl_profile_id,
        action=bootstrap_result.action,
        domain_count=bootstrap_result.domain_count,
    )


worker_app = build_worker(broker, service_name="search_worker", queue="search", on_startup=_startup)

__all__ = ["worker_app"]

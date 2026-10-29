"""Search Worker (очередь ``search``).

Запуск: taskiq worker apps.search.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.search.config import SearchSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = SearchSettings.model_validate(
    load_merged_config(service_name="search_worker", silent=True)
)
setup_worker_logging_early("search_worker", logging_config=_settings.logging)
set_settings(_settings)
set_files_route_segment(resolve_files_route_segment("search_worker"))

from apps.search.config import get_search_settings
from apps.search.services.crawl.bootstrap_service import CrawlBootstrapService
from apps.search.di import SearchDi
from apps.worker_manifest import wire_worker
from core.crawl.logging_events import log_crawl_bootstrap
from core.di import recipe
from core.tasks.worker_bootstrap import build_worker


async def ensure_crawl_pipeline(crawl_bootstrap_service: CrawlBootstrapService) -> None:
    bootstrap_result = await crawl_bootstrap_service.ensure_crawl_pipeline_ready()
    log_crawl_bootstrap(
        crawl_profile_id=bootstrap_result.crawl_profile_id,
        action=bootstrap_result.action,
        domain_count=bootstrap_result.domain_count,
    )


broker = wire_worker("search")
worker_app = build_worker(
    broker,
    service_name="search_worker",
    queue="search",
    settings=get_search_settings(),
    di_class=SearchDi,
    database="search_url",
    lifecycle=(recipe(ensure_crawl_pipeline),),
)

__all__ = ["worker_app"]

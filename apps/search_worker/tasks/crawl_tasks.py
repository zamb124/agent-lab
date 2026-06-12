"""Crawl TaskIQ tasks for search worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.search.container import get_search_container
from apps.search.services.system_context import build_search_system_context
from apps.search_worker.broker import broker
from apps.search_worker.tasks.task_names import (
    CRAWL_DISCOVER_DOMAIN_TASK_NAME,
    CRAWL_FETCH_URL_TASK_NAME,
    CRAWL_IMPORT_SEED_DOMAINS_TASK_NAME,
    CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
    CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
)
from core.context import clear_context, set_context
from core.crawl.models import CrawlOrchestratorTickResult, CrawlSeedSource, SeedImportRequest
from core.types import JsonObject, require_json_object


async def _enter_worker_context(*, trace_id: str) -> None:
    container = get_search_container()
    set_context(
        await build_search_system_context(
            trace_id=trace_id,
            company_repository=container.company_repository,
            subdomain_repository=container.subdomain_repository,
            user_repository=container.user_repository,
        )
    )


@broker.task(
    task_name=CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
    queue_name="search",
    retry_on_error=True,
    max_retries=1,
)
async def crawl_orchestrator_tick(
    crawl_profile_id: str,
    schedule_task_id: str | None = None,
) -> CrawlOrchestratorTickResult:
    trace_id = f"crawl:tick:{crawl_profile_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        container = get_search_container()
        return await container.crawl_orchestrator_service.run_tick(
            crawl_profile_id=crawl_profile_id,
            trigger="scheduler" if schedule_task_id else "manual",
            schedule_task_id=schedule_task_id,
        )
    finally:
        clear_context()


@broker.task(
    task_name=CRAWL_DISCOVER_DOMAIN_TASK_NAME,
    queue_name="search",
    retry_on_error=True,
    max_retries=2,
)
async def crawl_discover_domain(
    crawl_domain_id: str,
    crawl_job_id: str,
    crawl_profile_id: str,
) -> JsonObject:
    trace_id = f"crawl:discover:{crawl_domain_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        container = get_search_container()
        await container.crawl_orchestrator_service.discover_domain(
            crawl_domain_id,
            crawl_job_id,
            crawl_profile_id,
        )
        return {"crawl_domain_id": crawl_domain_id, "status": "discovered"}
    finally:
        clear_context()


@broker.task(
    task_name=CRAWL_FETCH_URL_TASK_NAME,
    queue_name="search",
    retry_on_error=True,
    max_retries=3,
)
async def crawl_fetch_url(
    crawl_domain_id: str,
    crawl_job_id: str,
    crawl_profile_id: str,
    url_budget: int,
) -> JsonObject:
    trace_id = f"crawl:fetch:{crawl_domain_id}:{crawl_job_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        container = get_search_container()
        await container.crawl_orchestrator_service.fetch_one_url(
            crawl_domain_id,
            crawl_job_id,
            crawl_profile_id,
            url_budget,
        )
        return {"crawl_domain_id": crawl_domain_id, "status": "fetched"}
    finally:
        clear_context()


@broker.task(
    task_name=CRAWL_IMPORT_SEED_DOMAINS_TASK_NAME,
    queue_name="search",
    retry_on_error=False,
    max_retries=0,
)
async def crawl_import_seed_domains(
    crawl_profile_id: str,
    seed_source: CrawlSeedSource,
    tranco_limit: int,
) -> JsonObject:
    trace_id = f"crawl:seed:{crawl_profile_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        container = get_search_container()
        result = await container.crawl_orchestrator_service.import_seed(
            SeedImportRequest(
                crawl_profile_id=crawl_profile_id,
                seed_source=seed_source,
                tranco_limit=tranco_limit,
            )
        )
        if result.imported > 0:
            tick_task = broker.find_task(CRAWL_ORCHESTRATOR_TICK_TASK_NAME)
            if tick_task is None:
                raise RuntimeError(f"task is not registered: {CRAWL_ORCHESTRATOR_TICK_TASK_NAME}")
            _ = await tick_task.kiq(crawl_profile_id)
        return require_json_object(result.model_dump(mode="json"), "seed import result")
    finally:
        clear_context()


@broker.task(
    task_name=CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
    queue_name="search",
    retry_on_error=True,
    max_retries=1,
)
async def crawl_reclaim_stale_fetching() -> JsonObject:
    trace_id = f"crawl:reclaim:{datetime.now(UTC).isoformat()}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        container = get_search_container()
        reclaimed = await container.crawl_url_repository.reclaim_stale_fetching(
            stale_before=datetime.now(UTC) - timedelta(minutes=30),
        )
        return {"reclaimed": reclaimed}
    finally:
        clear_context()

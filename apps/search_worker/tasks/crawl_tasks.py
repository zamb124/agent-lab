"""Crawl TaskIQ tasks for search worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.search.config import get_search_settings
from apps.search_worker.di import Di
from apps.search_worker.tasks.task_names import (
    CRAWL_DISCOVER_DOMAIN,
    CRAWL_ENRICH_URL,
    CRAWL_FETCH_URL,
    CRAWL_IMPORT_SEED_DOMAINS,
    CRAWL_ORCHESTRATOR_TICK,
    CRAWL_RECLAIM_STALE_FETCHING,
)
from core.context import clear_context, set_context
from core.crawl.logging_events import log_crawl_reclaim_completed
from core.crawl.models import (
    CrawlJob,
    CrawlOrchestratorTickResult,
    CrawlProfile,
    CrawlSeedSource,
    CrawlUrl,
    SeedImportRequest,
)
from core.identity.system_bootstrap import build_system_admin_job_context
from core.tasks import enqueue, platform_task
from core.types import JsonObject, require_json_object


async def _enter_worker_context(*, trace_id: str) -> None:
    _ = set_context(
        await build_system_admin_job_context(
            trace_id=trace_id,
            session_id=f"search:{trace_id}",
            channel="search",
        )
    )


@platform_task(CRAWL_ORCHESTRATOR_TICK)
async def crawl_orchestrator_tick(
    crawl_profile_id: str,
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> CrawlOrchestratorTickResult:
    _ = company_id
    trace_id = f"crawl:tick:{crawl_profile_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        return await di.crawl_orchestrator_service.run_tick(
            crawl_profile_id=crawl_profile_id,
            trigger="scheduler" if schedule_task_id else "manual",
            schedule_task_id=schedule_task_id,
        )
    finally:
        clear_context()


@platform_task(CRAWL_DISCOVER_DOMAIN)
async def crawl_discover_domain(
    crawl_domain_id: str,
    crawl_job_id: str,
    crawl_profile_id: str,
    *,
    di: Di,
) -> JsonObject:
    trace_id = f"crawl:discover:{crawl_domain_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        await di.crawl_orchestrator_service.discover_domain(
            crawl_domain_id,
            crawl_job_id,
            crawl_profile_id,
        )
        return {"crawl_domain_id": crawl_domain_id, "status": "discovered"}
    finally:
        clear_context()


@platform_task(CRAWL_FETCH_URL)
async def crawl_fetch_url(
    crawl_domain_id: str,
    crawl_job_id: str,
    crawl_profile_id: str,
    url_budget: int,
    *,
    di: Di,
) -> JsonObject:
    trace_id = f"crawl:fetch:{crawl_domain_id}:{crawl_job_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        await di.crawl_orchestrator_service.fetch_one_url(
            crawl_domain_id,
            crawl_job_id,
            crawl_profile_id,
            url_budget,
        )
        return {"crawl_domain_id": crawl_domain_id, "status": "fetched"}
    finally:
        clear_context()


@platform_task(CRAWL_ENRICH_URL)
async def crawl_enrich_url(
    crawl_url_id: str,
    crawl_job_id: str,
    crawl_profile_id: str,
    *,
    di: Di,
) -> JsonObject:
    trace_id = f"crawl:enrich:{crawl_url_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        await di.crawl_orchestrator_service.enrich_one_url(
            crawl_url_id,
            crawl_job_id,
            crawl_profile_id,
        )
        return {"crawl_url_id": crawl_url_id, "status": "enriched"}
    finally:
        clear_context()


@platform_task(CRAWL_IMPORT_SEED_DOMAINS)
async def crawl_import_seed_domains(
    crawl_profile_id: str,
    seed_source: CrawlSeedSource,
    tranco_limit: int,
    *,
    di: Di,
) -> JsonObject:
    trace_id = f"crawl:seed:{crawl_profile_id}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        result = await di.crawl_orchestrator_service.import_seed(
            SeedImportRequest(
                crawl_profile_id=crawl_profile_id,
                seed_source=seed_source,
                tranco_limit=tranco_limit,
            )
        )
        if result.imported > 0:
            _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, crawl_profile_id)
        return require_json_object(result.model_dump(mode="json"), "seed import result")
    finally:
        clear_context()


@platform_task(CRAWL_RECLAIM_STALE_FETCHING)
async def crawl_reclaim_stale_fetching(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    _ = schedule_task_id, company_id
    trace_id = f"crawl:reclaim:{datetime.now(UTC).isoformat()}"
    await _enter_worker_context(trace_id=trace_id)
    try:
        stale_before = datetime.now(UTC) - timedelta(hours=6)
        stale_jobs = await CrawlJob.finish_stale_running_jobs(
            stale_before=stale_before,
        )
        reclaimed_fetching = await CrawlUrl.reclaim_stale_fetching(
            stale_before=datetime.now(UTC) - timedelta(minutes=30),
        )
        requeued_failed = await CrawlUrl.requeue_failed_urls()
        crawl_profile_id = get_search_settings().crawl.default_crawl_profile_id
        profile_bundle = await CrawlProfile.require_with_index(crawl_profile_id)
        enrichment_backfill = 0
        if profile_bundle.profile.llm_enrichment_enabled:
            missing_ids = await CrawlUrl.list_indexed_missing_enrichment(
                crawl_profile_id,
                limit=50,
            )
            if missing_ids:
                backfill_job = await CrawlJob.start(
                    crawl_profile_id,
                    "scheduler",
                    schedule_task_id,
                )
                enrichment_backfill = await di.crawl_orchestrator_service.enqueue_enrichment_backfill(
                    crawl_profile_id,
                    backfill_job.crawl_job_id,
                    limit=50,
                )
                _ = await CrawlJob.finish(
                    backfill_job.crawl_job_id,
                    status="completed",
                )
        pending_urls = await CrawlUrl.count_pending_for_profile(crawl_profile_id)
        log_crawl_reclaim_completed(
            crawl_profile_id=crawl_profile_id,
            stale_jobs_finished=stale_jobs,
            reclaimed_fetching=reclaimed_fetching,
            requeued_failed=requeued_failed,
            pending_urls=pending_urls,
        )
        if pending_urls > 0:
            _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, crawl_profile_id)
        return {
            "stale_jobs_finished": stale_jobs,
            "reclaimed_fetching": reclaimed_fetching,
            "requeued_failed": requeued_failed,
            "enrichment_backfill": enrichment_backfill,
        }
    finally:
        clear_context()

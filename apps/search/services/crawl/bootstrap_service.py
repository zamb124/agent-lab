"""Idempotent crawl pipeline bootstrap on worker startup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.search.config import SearchCrawlConfig
from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from apps.search_worker.tasks.task_names import (
    CRAWL_IMPORT_SEED_DOMAINS,
    CRAWL_ORCHESTRATOR_TICK,
)
from core.crawl.models import CrawlBootstrapResult
from core.tasks import enqueue


class CrawlBootstrapService:
    def __init__(
        self,
        *,
        crawl_profile_repository: CrawlProfileRepository,
        crawl_domain_repository: CrawlDomainRepository,
        crawl_url_repository: CrawlUrlRepository,
        crawl_job_repository: CrawlJobRepository,
        crawl_config: SearchCrawlConfig,
    ) -> None:
        self._crawl_profile_repository: CrawlProfileRepository = crawl_profile_repository
        self._crawl_domain_repository: CrawlDomainRepository = crawl_domain_repository
        self._crawl_url_repository: CrawlUrlRepository = crawl_url_repository
        self._crawl_job_repository: CrawlJobRepository = crawl_job_repository
        self._crawl_config: SearchCrawlConfig = crawl_config

    async def ensure_crawl_pipeline_ready(self) -> CrawlBootstrapResult:
        crawl_profile_id = self._crawl_config.default_crawl_profile_id
        stale_before = datetime.now(UTC) - timedelta(hours=6)
        _ = await self._crawl_job_repository.finish_stale_running_jobs(stale_before=stale_before)

        if not self._crawl_config.bootstrap_tranco_on_empty:
            domain_count = await self._crawl_domain_repository.count_for_profile(crawl_profile_id)
            pending_urls = await self._crawl_url_repository.count_pending_for_profile(crawl_profile_id)
            if pending_urls > 0:
                _ = await enqueue(
                    CRAWL_ORCHESTRATOR_TICK,
                    crawl_profile_id,
                    background_kind="startup",
                )
            return CrawlBootstrapResult(
                crawl_profile_id=crawl_profile_id,
                action="bootstrap_disabled",
                domain_count=domain_count,
            )

        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")

        domain_count = await self._crawl_domain_repository.count_for_profile(crawl_profile_id)
        if domain_count > 0:
            pending_urls = await self._crawl_url_repository.count_pending_for_profile(crawl_profile_id)
            if pending_urls > 0:
                _ = await enqueue(
                    CRAWL_ORCHESTRATOR_TICK,
                    crawl_profile_id,
                    background_kind="startup",
                )
            return CrawlBootstrapResult(
                crawl_profile_id=crawl_profile_id,
                action="skipped_seed",
                domain_count=domain_count,
            )

        _ = await enqueue(
            CRAWL_IMPORT_SEED_DOMAINS,
            crawl_profile_id,
            "tranco",
            self._crawl_config.tranco_seed_limit,
            background_kind="startup",
        )
        return CrawlBootstrapResult(
            crawl_profile_id=crawl_profile_id,
            action="queued_seed",
            domain_count=0,
        )

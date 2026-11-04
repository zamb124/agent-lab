"""Idempotent crawl pipeline bootstrap on worker startup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from oxyde.exceptions import IntegrityError

from apps.search.config import SearchCrawlConfig
from apps.search.models import (
    CrawlBootstrapResult,
    CrawlDomain,
    CrawlJob,
    CrawlProfile,
    CrawlProfileCreateRequest,
    CrawlUrl,
)
from apps.search.tasks.task_names import (
    CRAWL_IMPORT_SEED_DOMAINS,
    CRAWL_ORCHESTRATOR_TICK,
)
from core.models.identity_models import SYSTEM_COMPANY_ID
from core.search.index_models import SearchIndexDefinition
from core.tasks import enqueue

RUNET_SEARCH_INDEX_ID = "runet"
RUNET_PLATFORM_CRAWL_PROFILE_ID = "runet_platform"


async def ensure_runet_platform_seeded() -> None:
    """Идемпотентный сид платформенного индекса ``runet`` и профиля ``runet_platform``."""
    now = datetime.now(UTC)
    index = await SearchIndexDefinition.by_search_index_id(
        SYSTEM_COMPANY_ID, RUNET_SEARCH_INDEX_ID
    )
    if index is None:
        try:
            _ = await SearchIndexDefinition.create(
                SearchIndexDefinition(
                    search_index_id=RUNET_SEARCH_INDEX_ID,
                    company_id=SYSTEM_COMPANY_ID,
                    display_name="Runet Web",
                    description="Платформенный индекс русскоязычного веба",
                    rag_namespace_id="runet:platform",
                    rag_collection_id="runet",
                    search_enabled=True,
                    indexing_profile_key="runet_web",
                    created_at=now,
                    updated_at=now,
                )
            )
        except IntegrityError:
            if (
                await SearchIndexDefinition.by_search_index_id(
                    SYSTEM_COMPANY_ID, RUNET_SEARCH_INDEX_ID
                )
                is None
            ):
                raise
    profile = await CrawlProfile.objects.filter(
        crawl_profile_id=RUNET_PLATFORM_CRAWL_PROFILE_ID
    ).get_or_none()
    if profile is None:
        try:
            _ = await CrawlProfile.create(
                CrawlProfileCreateRequest(
                    crawl_profile_id=RUNET_PLATFORM_CRAWL_PROFILE_ID,
                    search_index_id=RUNET_SEARCH_INDEX_ID,
                    seed_source="tranco",
                    browser_fallback_enabled=True,
                )
            )
        except IntegrityError:
            if (
                await CrawlProfile.objects.filter(
                    crawl_profile_id=RUNET_PLATFORM_CRAWL_PROFILE_ID
                ).get_or_none()
                is None
            ):
                raise


class CrawlBootstrapService:
    def __init__(self, *, crawl_config: SearchCrawlConfig) -> None:
        self._crawl_config: SearchCrawlConfig = crawl_config

    async def ensure_crawl_pipeline_ready(self) -> CrawlBootstrapResult:
        crawl_profile_id = self._crawl_config.default_crawl_profile_id
        stale_before = datetime.now(UTC) - timedelta(hours=6)
        _ = await CrawlJob.finish_stale_running_jobs(stale_before=stale_before)
        if crawl_profile_id == RUNET_PLATFORM_CRAWL_PROFILE_ID:
            await ensure_runet_platform_seeded()

        if not self._crawl_config.bootstrap_tranco_on_empty:
            domain_count = await CrawlDomain.count_for_profile(crawl_profile_id)
            pending_urls = await CrawlUrl.count_pending_for_profile(crawl_profile_id)
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

        profile_bundle = await CrawlProfile.require_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")

        domain_count = await CrawlDomain.count_for_profile(crawl_profile_id)
        if domain_count > 0:
            pending_urls = await CrawlUrl.count_pending_for_profile(crawl_profile_id)
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

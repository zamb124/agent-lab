"""Короткий extract помечает URL skipped через реальные CrawlUrl и CrawlJob."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiohttp import web

from apps.search.config import get_search_settings
from apps.search.services.crawl.fetch_service import CrawlFetchService
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from apps.search.services.crawl.page_enrichment_service import CrawlPageEnrichmentService
from apps.search.services.crawl.politeness_service import CrawlPolitenessService
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.crawl.models import (
    CrawlDomain,
    CrawlJob,
    CrawlProfile,
    CrawlProfileWithIndex,
    CrawlUrl,
    SitemapEntry,
)
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server

_THIN_HTML = (
    "<html><head><title>Thin</title></head>"
    "<body><p>Short crawl extract.</p></body></html>"
)


def _thin_app() -> web.Application:
    async def page(_request: web.Request) -> web.Response:
        return web.Response(text=_THIN_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/thin", page)
    return app


@pytest.mark.asyncio
async def test_fetch_marks_skipped_on_extract_too_short(unique_id: str) -> None:
    domain_id = f"dom-{unique_id}"
    profile_id = f"cr-{unique_id}"[:64]
    now = datetime.now(UTC)
    crawl_config = get_search_settings().crawl.model_copy(update={"politeness_enabled": False})
    job = await CrawlJob.start(profile_id, "manual", None)
    async with ephemeral_web_server(_thin_app()) as base_url:
        page_url = f"{base_url}/thin"
        _ = await CrawlUrl.upsert_from_sitemap(domain_id, [SitemapEntry(url=page_url)])
        stored = await CrawlUrl.objects.filter(crawl_domain_id=domain_id, url=page_url).get()
        profile = CrawlProfile(
            crawl_profile_id=profile_id,
            search_index_id=f"idx-{unique_id}"[:64],
            enabled=True,
            seed_source="manual",
            refresh_interval_seconds=21600,
            max_urls_per_domain_per_tick=10,
            max_domains_per_tick=2,
            max_urls_per_batch=5,
            http_concurrency=2,
            browser_fallback_enabled=False,
            sitemap_stale_after_seconds=86400,
            llm_enrichment_enabled=False,
            created_at=now,
            updated_at=now,
        )
        search_index = SearchIndexDefinition(
            search_index_id=profile.search_index_id,
            company_id="system",
            display_name="Thin",
            rag_namespace_id=f"{profile.search_index_id}:ns",
            rag_collection_id=profile.search_index_id,
            enabled=True,
            search_enabled=True,
            created_at=now,
            updated_at=now,
        )
        domain = CrawlDomain(
            crawl_domain_id=domain_id,
            crawl_profile_id=profile_id,
            domain="127.0.0.1",
            category="unknown",
            status="active",
            next_crawl_after=now,
            created_at=now,
            updated_at=now,
        )
        orchestrator = CrawlOrchestratorService(
            fetch_service=CrawlFetchService(
                browser_fetch_client=BrowserFetchClient(ServiceClient()),
                browser_fetch_timeout_seconds=crawl_config.browser_fetch_timeout_seconds,
            ),
            page_enrichment_service=CrawlPageEnrichmentService(crawl_config.enrichment),
            politeness_service=CrawlPolitenessService(
                redis_client=RedisClient(get_settings().database.redis_url),
                crawl_config=crawl_config,
            ),
            rag_client=RagClient(),
            crawl_config=crawl_config,
        )
        try:
            await orchestrator._fetch_and_index_url(
                crawl_url=stored,
                crawl_job_id=job.crawl_job_id,
                crawl_profile_id=profile_id,
                profile_bundle=CrawlProfileWithIndex(profile=profile, search_index=search_index),
                domain=domain,
                stored_extract_hash=None,
            )
            skipped = await CrawlUrl.get(stored.crawl_url_id)
            finished = await CrawlJob.get(job.crawl_job_id)
            assert skipped.crawl_status == "skipped"
            assert finished.urls_skipped == 1
            assert finished.errors == 0
        finally:
            _ = await CrawlUrl.delete_by_id(stored.crawl_url_id)
            _ = await CrawlJob.delete_by_id(job.crawl_job_id)

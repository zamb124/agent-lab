"""Layer 1 индексирует страницу и ставит enrich только при включённом LLM."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiohttp import web

import apps.search.services.crawl.orchestrator_service as orchestrator_module
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
from apps.search.models import (
    CrawlDomain,
    CrawlJob,
    CrawlProfile,
    CrawlProfileWithIndex,
    CrawlUrl,
    SitemapEntry,
)
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server
from tests.fixtures.taskiq_capture import taskiq_task_name

_LONG_HTML = (
    "<html><head><title>Layer one page</title></head><body>"
    "<h1>Layer one page</h1>"
    "<p>This crawl fixture carries enough visible prose for the extract minimum. "
    "The page describes a local documentation sample used only by the search test. "
    "It mentions indexes, fetches, and the raw markdown stored before any enrichment. "
    "The sentences stay on the page so the extractor keeps a title and a body.</p>"
    "</body></html>"
)


def _long_app() -> web.Application:
    async def page(_request: web.Request) -> web.Response:
        return web.Response(text=_LONG_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/page", page)
    return app


def _record_enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    recorded: list[tuple[object, ...]] = []

    async def record(task: object, *args: object, **kwargs: object) -> None:
        _ = kwargs
        recorded.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(orchestrator_module, "enqueue", record)
    return recorded


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.parametrize("llm_enrichment_enabled", [True, False])
async def test_layer1_enqueues_enrich_only_when_llm_enabled(
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
    llm_enrichment_enabled: bool,
) -> None:
    recorded = _record_enqueued(monkeypatch)
    domain_id = f"dom-{unique_id}-{'on' if llm_enrichment_enabled else 'off'}"
    profile_id = f"cr-{unique_id}-{'on' if llm_enrichment_enabled else 'off'}"[:64]
    search_index_id = f"ly-{unique_id}-{'on' if llm_enrichment_enabled else 'off'}"[:64]
    now = datetime.now(UTC)
    crawl_config = get_search_settings().crawl.model_copy(update={"politeness_enabled": False})
    job = await CrawlJob.start(profile_id, "manual", None)
    rag_client = RagClient()
    namespace_id = f"{search_index_id}:ns"
    namespace_created = False
    stored_id: str | None = None
    async with ephemeral_web_server(_long_app()) as base_url:
        page_url = f"{base_url}/page"
        _ = await CrawlUrl.upsert_from_sitemap(domain_id, [SitemapEntry(url=page_url)])
        stored = await CrawlUrl.objects.filter(crawl_domain_id=domain_id, url=page_url).get()
        stored_id = stored.crawl_url_id
        profile = CrawlProfile(
            crawl_profile_id=profile_id,
            search_index_id=search_index_id,
            enabled=True,
            seed_source="manual",
            refresh_interval_seconds=21600,
            max_urls_per_domain_per_tick=10,
            max_domains_per_tick=2,
            max_urls_per_batch=5,
            http_concurrency=2,
            browser_fallback_enabled=False,
            sitemap_stale_after_seconds=86400,
            llm_enrichment_enabled=llm_enrichment_enabled,
            created_at=now,
            updated_at=now,
        )
        search_index = SearchIndexDefinition(
            search_index_id=search_index_id,
            company_id="system",
            display_name="Layer one",
            rag_namespace_id=namespace_id,
            rag_collection_id=search_index_id,
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
            rag_client=rag_client,
            crawl_config=crawl_config,
        )
        try:
            _ = await rag_client.create_namespace(namespace_id)
            namespace_created = True
            await orchestrator._fetch_and_index_url(
                crawl_url=stored,
                crawl_job_id=job.crawl_job_id,
                crawl_profile_id=profile_id,
                profile_bundle=CrawlProfileWithIndex(profile=profile, search_index=search_index),
                domain=domain,
                stored_extract_hash=None,
            )
            indexed = await CrawlUrl.get(stored.crawl_url_id)
            finished = await CrawlJob.get(job.crawl_job_id)
            enrich_tasks = [item for item in recorded if item[0] == "crawl_enrich_url"]
            assert indexed.crawl_status == "indexed"
            assert indexed.document_id is not None
            assert indexed.enriched_content_hash is None
            assert finished.urls_indexed == 1
            if llm_enrichment_enabled:
                assert enrich_tasks == [(
                    "crawl_enrich_url",
                    stored.crawl_url_id,
                    job.crawl_job_id,
                    profile_id,
                )]
            else:
                assert enrich_tasks == []
        finally:
            if stored_id is not None:
                _ = await CrawlUrl.delete_by_id(stored_id)
            _ = await CrawlJob.delete_by_id(job.crawl_job_id)
            if namespace_created:
                _ = await rag_client.delete_namespace(namespace_id)

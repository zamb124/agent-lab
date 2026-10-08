"""Backfill enrichment ставит crawl_enrich_url только для indexed URL без enriched hash."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainSeed,
    CrawlProfile,
    CrawlProfileCreateRequest,
    CrawlStructuralSignals,
    CrawlUrl,
    SitemapEntry,
)
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.taskiq_capture import taskiq_task_name


def _record_enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    recorded: list[tuple[object, ...]] = []

    async def record(task: object, *args: object, **kwargs: object) -> None:
        _ = kwargs
        recorded.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(orchestrator_module, "enqueue", record)
    return recorded


@pytest.mark.asyncio
async def test_enqueue_enrichment_backfill_enqueues_missing_urls(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    now = datetime.now(UTC)
    search_index_id = f"bf-{unique_id}"[:64]
    crawl_profile_id = f"cr-{unique_id}"[:64]
    await SearchIndexDefinition.create(
        SearchIndexDefinition(
            search_index_id=search_index_id,
            company_id="system",
            display_name=f"Backfill {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
            created_at=now,
            updated_at=now,
        )
    )
    await CrawlProfile.create(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            browser_fallback_enabled=False,
        )
    )
    await CrawlProfile.set_llm_enrichment(
        crawl_profile_id,
        llm_enrichment_enabled=True,
        enrichment_model="test-enrichment-model",
    )
    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=f"{unique_id}.example", category="docs", domain_rank=1)],
        next_crawl_after=now,
    )
    domain = await CrawlDomain.objects.filter(crawl_profile_id=crawl_profile_id).get()
    missing_a = f"https://{unique_id}.example/a"
    missing_b = f"https://{unique_id}.example/b"
    enriched = f"https://{unique_id}.example/done"
    _ = await CrawlUrl.upsert_from_sitemap(
        domain.crawl_domain_id,
        [SitemapEntry(url=missing_a), SitemapEntry(url=missing_b), SitemapEntry(url=enriched)],
    )
    rows = await CrawlUrl.objects.filter(crawl_domain_id=domain.crawl_domain_id).all()
    by_url = {row.url: row for row in rows}
    for url in (missing_a, missing_b):
        await CrawlUrl.mark_indexed(
            by_url[url].crawl_url_id,
            f"doc-{url[-1]}",
            "hash",
            "http",
            extract_markdown="# Missing\n\nbody",
            extract_title="Missing",
            extract_structural_signals=CrawlStructuralSignals(title="Missing"),
        )
    await CrawlUrl.mark_indexed(
        by_url[enriched].crawl_url_id,
        "doc-done",
        "hash-done",
        "http",
        extract_markdown="# Done\n\nbody",
        extract_title="Done",
        extract_structural_signals=CrawlStructuralSignals(title="Done"),
        enriched_content_hash="enriched-hash",
    )
    recorded = _record_enqueued(monkeypatch)
    crawl_config = get_search_settings().crawl
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
        count = await orchestrator.enqueue_enrichment_backfill(
            crawl_profile_id,
            "job-backfill",
            limit=100,
        )
        enrich_tasks = [item for item in recorded if item[0] == "crawl_enrich_url"]
        assert count == 2
        assert {item[1] for item in enrich_tasks} == {
            by_url[missing_a].crawl_url_id,
            by_url[missing_b].crawl_url_id,
        }
        assert all(item[2:] == ("job-backfill", crawl_profile_id) for item in enrich_tasks)
    finally:
        for row in rows:
            _ = await CrawlUrl.delete_by_id(row.crawl_url_id)
        _ = await CrawlDomain.delete_by_id(domain.crawl_domain_id)
        _ = await CrawlProfile.delete_by_id(crawl_profile_id)
        _ = await SearchIndexDefinition.delete_by_id(search_index_id)

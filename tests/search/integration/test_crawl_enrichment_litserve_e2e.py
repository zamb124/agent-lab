"""Crawl enrichment E2E: real HTTP fetch + LitServe LLM + RAG ingest."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.search_worker.tasks.crawl_tasks import crawl_discover_domain, crawl_fetch_url
from core.crawl.models import CrawlDomainSeed, CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug
from tests.search.integration.crawl_strict_e2e_support import (
    CRAWL_STRICT_ENRICHMENT_MODEL,
    poll_enriched_urls,
    poll_index_search_hits,
    require_crawl_llm_live_gate,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(600, func_only=True),
]

REAL_CRAWL_DOMAIN = "example.com"
REAL_CRAWL_QUERY = "documentation examples"


@pytest.mark.asyncio
async def test_crawl_enrichment_indexes_example_com_with_page_summary(
    search_client,
    rag_worker,
    search_worker,
    provider_litserve_service,
    provider_litserve_crawl_llm_service,
    crawl_search_container,
    search_system_context,
    unique_id,
):
    require_crawl_llm_live_gate()
    _ = (
        search_worker,
        rag_worker,
        provider_litserve_service,
        provider_litserve_crawl_llm_service,
        search_system_context,
    )
    search_container = crawl_search_container
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Crawl enrichment {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_container.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            max_urls_per_domain_per_tick=1,
            browser_fallback_enabled=False,
        )
    )
    await search_container.crawl_profile_repository.set_llm_enrichment(
        crawl_profile_id,
        llm_enrichment_enabled=True,
        enrichment_model=CRAWL_STRICT_ENRICHMENT_MODEL,
    )

    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=REAL_CRAWL_DOMAIN, category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    domain = (
        await search_container.crawl_domain_repository.list_due(
            crawl_profile_id,
            now=datetime.now(UTC),
            limit=1,
        )
    )[0]
    job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )
    _ = await crawl_discover_domain(domain.crawl_domain_id, job.crawl_job_id, crawl_profile_id)
    _ = await crawl_fetch_url(domain.crawl_domain_id, job.crawl_job_id, crawl_profile_id, 1)

    job_after_fetch = await search_container.crawl_job_repository.get(job.crawl_job_id)
    assert job_after_fetch.urls_indexed >= 1

    await poll_enriched_urls(
        search_client,
        crawl_profile_id=crawl_profile_id,
        min_enriched=1,
        timeout_seconds=300.0,
    )

    job_after = await search_container.crawl_job_repository.get(job.crawl_job_id)
    assert job_after.urls_enriched >= 1

    hit = await poll_index_search_hits(
        search_client,
        search_index_id=search_index_id,
        query=REAL_CRAWL_QUERY,
        url_domain=REAL_CRAWL_DOMAIN,
        content_marker="Example",
        timeout_seconds=120.0,
    )
    assert hit["search_index_id"] == search_index_id

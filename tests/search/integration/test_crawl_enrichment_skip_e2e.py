"""Second crawl fetch with enrichment enabled should skip unchanged URL."""

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
    require_crawl_humanitec_llm_live_gate,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(600, func_only=True),
]

REAL_CRAWL_DOMAIN = "example.com"


@pytest.mark.asyncio
async def test_crawl_enrichment_second_fetch_skips_unchanged_url(
    search_client,
    search_worker,
    provider_litserve_service,
    crawl_search_container,
    unique_id,
):
    require_crawl_humanitec_llm_live_gate()
    _ = provider_litserve_service, search_worker
    search_container = crawl_search_container
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Crawl skip {unique_id}",
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
    first_job = await search_container.crawl_job_repository.get(job.crawl_job_id)
    assert first_job.urls_indexed >= 1

    url_page = await search_container.crawl_url_repository.list_page_for_profile(
        crawl_profile_id=crawl_profile_id,
        crawl_status="indexed",
        domain=REAL_CRAWL_DOMAIN,
        limit=1,
        offset=0,
    )
    assert url_page.total >= 1
    crawl_url_id = url_page.items[0].crawl_url_id

    await poll_enriched_urls(
        search_client,
        crawl_profile_id=crawl_profile_id,
        min_enriched=1,
        timeout_seconds=120.0,
    )

    await search_container.crawl_url_repository.requeue_indexed_for_content_recheck(crawl_url_id)

    second_job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )
    _ = await crawl_fetch_url(domain.crawl_domain_id, second_job.crawl_job_id, crawl_profile_id, 1)
    second_after = await search_container.crawl_job_repository.get(second_job.crawl_job_id)
    assert second_after.urls_skipped >= 1
    assert second_after.urls_enriched == 0

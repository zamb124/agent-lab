"""Second crawl fetch with enrichment enabled should skip unchanged URL."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.search.tasks.crawl_tasks import crawl_discover_domain, crawl_fetch_url
from apps.search.models import (
    CrawlDomain,
    CrawlDomainSeed,
    CrawlJob,
    CrawlProfile,
    CrawlProfileCreateRequest,
    CrawlUrl,
)
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
    crawl_search_di,
    unique_id,
):
    require_crawl_humanitec_llm_live_gate()
    _ = provider_litserve_service, search_worker
    search_di = crawl_search_di
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    await search_di.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Crawl skip {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_di.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            max_urls_per_domain_per_tick=1,
            browser_fallback_enabled=False,
        )
    )
    await CrawlProfile.update_llm_enrichment_enabled_and_model(
        crawl_profile_id,
        llm_enrichment_enabled=True,
        enrichment_model=CRAWL_STRICT_ENRICHMENT_MODEL,
    )

    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=REAL_CRAWL_DOMAIN, category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    domain = (
        await CrawlDomain.list_due_by_next_crawl_after_asc(
            crawl_profile_id,
            now=datetime.now(UTC),
            limit=1,
        )
    )[0]
    job = await CrawlJob.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )
    _ = await crawl_discover_domain(
        domain.crawl_domain_id, job.crawl_job_id, crawl_profile_id, di=search_di
    )
    _ = await crawl_fetch_url(
        domain.crawl_domain_id, job.crawl_job_id, crawl_profile_id, 1, di=search_di
    )
    first_job = await CrawlJob.get(job.crawl_job_id)
    assert first_job.urls_indexed >= 1

    url_page = await CrawlUrl.page_for_profile_by_updated_at_desc(
        crawl_profile_id=crawl_profile_id,
        crawl_status="indexed",
        domain=REAL_CRAWL_DOMAIN,
        content_type=None,
        primary_topic=None,
        enriched_only=None,
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

    await CrawlUrl.requeue_indexed_for_content_recheck(crawl_url_id)

    second_job = await CrawlJob.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )
    _ = await crawl_fetch_url(
        domain.crawl_domain_id, second_job.crawl_job_id, crawl_profile_id, 1, di=search_di
    )
    second_after = await CrawlJob.get(second_job.crawl_job_id)
    assert second_after.urls_skipped >= 1
    assert second_after.urls_enriched == 0

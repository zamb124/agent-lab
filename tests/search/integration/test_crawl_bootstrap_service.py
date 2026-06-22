"""CrawlBootstrapService idempotency without TaskIQ."""

from datetime import UTC, datetime

import pytest

from apps.search.config import SearchCrawlConfig
from apps.search.services.crawl.bootstrap_service import CrawlBootstrapService
from core.crawl.models import CrawlDomainSeed, CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(60, func_only=True)


async def _create_empty_profile(search_container, unique_id: str) -> str:
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Bootstrap {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_container.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            browser_fallback_enabled=False,
        )
    )
    return crawl_profile_id


@pytest.mark.asyncio
async def test_bootstrap_skips_seed_when_domains_exist(
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_empty_profile(search_container, unique_id)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="example.com", category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    before_count = await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id)

    bootstrap = CrawlBootstrapService(
        crawl_profile_repository=search_container.crawl_profile_repository,
        crawl_domain_repository=search_container.crawl_domain_repository,
        crawl_url_repository=search_container.crawl_url_repository,
        crawl_job_repository=search_container.crawl_job_repository,
        crawl_config=SearchCrawlConfig(
            default_crawl_profile_id=crawl_profile_id,
            bootstrap_tranco_on_empty=True,
            tranco_seed_limit=5,
        ),
    )
    result = await bootstrap.ensure_crawl_pipeline_ready()

    assert result.action == "skipped_seed"
    assert result.domain_count == before_count
    after_count = await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id)
    assert after_count == before_count


@pytest.mark.asyncio
async def test_bootstrap_disabled_does_not_queue_seed(
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_empty_profile(search_container, unique_id)
    assert await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id) == 0

    bootstrap = CrawlBootstrapService(
        crawl_profile_repository=search_container.crawl_profile_repository,
        crawl_domain_repository=search_container.crawl_domain_repository,
        crawl_url_repository=search_container.crawl_url_repository,
        crawl_job_repository=search_container.crawl_job_repository,
        crawl_config=SearchCrawlConfig(
            default_crawl_profile_id=crawl_profile_id,
            bootstrap_tranco_on_empty=False,
            tranco_seed_limit=5,
        ),
    )
    result = await bootstrap.ensure_crawl_pipeline_ready()

    assert result.action == "bootstrap_disabled"
    assert result.domain_count == 0
    assert await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id) == 0

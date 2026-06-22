"""Crawl bootstrap end-to-end via real TaskIQ search worker."""

import asyncio
import time

import pytest

from apps.search.config import SearchCrawlConfig
from apps.search.services.crawl.bootstrap_service import CrawlBootstrapService
from core.crawl.models import CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(120, func_only=True),
]


async def _poll_domain_count(crawl_domain_repository, crawl_profile_id: str, *, deadline: float) -> int:
    while time.monotonic() < deadline:
        count = await crawl_domain_repository.count_for_profile(crawl_profile_id)
        if count > 0:
            return count
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"crawl bootstrap timeout: no domains for profile {crawl_profile_id!r}"
    )


@pytest.mark.asyncio
async def test_bootstrap_queues_tranco_import_via_search_worker(
    search_container,
    search_worker,
    search_system_context,
    unique_id,
):
    _ = search_worker, search_system_context
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Bootstrap e2e {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_container.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="tranco",
            browser_fallback_enabled=False,
        )
    )
    assert await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id) == 0

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
    assert result.action == "queued_seed"
    assert result.domain_count == 0

    domain_count = await _poll_domain_count(
        search_container.crawl_domain_repository,
        crawl_profile_id,
        deadline=time.monotonic() + 90.0,
    )
    assert domain_count >= 1

    page = await search_container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=10,
        offset=0,
    )
    assert page.items

"""Real Tranco list download and crawl domain seed import."""

from datetime import UTC, datetime

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.seed_loader import import_tranco_domains
from core.crawl.models import CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(120, func_only=True)


@pytest.mark.asyncio
async def test_tranco_import_real_http_inserts_ru_domains(
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    rag_namespace_id = f"{search_index_id}:ns"

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Tranco seed {unique_id}",
            rag_namespace_id=rag_namespace_id,
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

    crawl_config = get_search_settings().crawl
    result = await import_tranco_domains(
        crawl_profile_id,
        crawl_domain_repository=search_container.crawl_domain_repository,
        limit=15,
        ru_com_whitelist=tuple(crawl_config.ru_com_whitelist),
        skip_categories=tuple(crawl_config.skip_categories),
    )

    assert result.imported >= 1
    domain_count = await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id)
    assert domain_count == result.imported

    page = await search_container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=50,
        offset=0,
    )
    assert page.items
    ru_domains = [
        item.domain
        for item in page.items
        if item.domain.endswith(".ru")
        or item.domain.endswith(".рф")
        or item.domain.endswith(".su")
        or item.domain in crawl_config.ru_com_whitelist
    ]
    assert ru_domains
    assert all(item.category not in crawl_config.skip_categories for item in page.items)
    assert all(item.next_crawl_after >= datetime.now(UTC) for item in page.items)

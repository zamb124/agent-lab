"""Обязательное чтение профиля обхода вместе с индексом поиска."""

from datetime import UTC, datetime

import pytest

from apps.search.models import CrawlProfile, CrawlProfileCreateRequest
from core.errors.boundary import PlatformNotFoundError
from core.search.index_models import SearchIndexDefinition


def _index(search_index_id: str, unique_id: str, now: datetime) -> SearchIndexDefinition:
    return SearchIndexDefinition(
        search_index_id=search_index_id,
        company_id="system",
        display_name=f"Index {unique_id}",
        rag_namespace_id=f"{search_index_id}:ns",
        rag_collection_id=search_index_id,
        created_at=now,
        updated_at=now,
    )


def _orphan_profile(crawl_profile_id: str, search_index_id: str, now: datetime) -> CrawlProfile:
    return CrawlProfile(
        crawl_profile_id=crawl_profile_id,
        search_index_id=search_index_id,
        seed_source="manual",
        refresh_interval_seconds=21600,
        max_urls_per_domain_per_tick=10,
        max_domains_per_tick=10,
        max_urls_per_batch=10,
        http_concurrency=2,
        browser_fallback_enabled=False,
        sitemap_stale_after_seconds=86400,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_require_with_index_returns_pair_or_not_found(unique_id: str) -> None:
    missing_profile_id = f"miss-{unique_id}"[:64]
    with pytest.raises(PlatformNotFoundError, match="crawl profile not found"):
        _ = await CrawlProfile.require_with_index(missing_profile_id)

    now = datetime(2026, 10, 26, tzinfo=UTC)
    search_index_id = f"ix-{unique_id}"[:64]
    crawl_profile_id = f"cr-{unique_id}"[:64]
    _ = await SearchIndexDefinition.create(_index(search_index_id, unique_id, now))
    created = await CrawlProfile.create(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            browser_fallback_enabled=False,
        )
    )
    loaded = await CrawlProfile.require_with_index(crawl_profile_id)
    assert created.profile.crawl_profile_id == crawl_profile_id
    assert loaded.profile.crawl_profile_id == crawl_profile_id
    assert loaded.search_index.search_index_id == search_index_id
    again = await CrawlProfile.require_with_index(crawl_profile_id)
    assert again.profile.crawl_profile_id == loaded.profile.crawl_profile_id
    assert again.search_index.search_index_id == loaded.search_index.search_index_id

    orphan_id = f"or-{unique_id}"[:64]
    _ = await CrawlProfile.objects.create(
        instance=_orphan_profile(orphan_id, f"gone-{unique_id}"[:64], now)
    )
    try:
        with pytest.raises(PlatformNotFoundError, match="search index not found"):
            _ = await CrawlProfile.require_with_index(orphan_id)
    finally:
        _ = await CrawlProfile.objects.filter(crawl_profile_id=orphan_id).delete()

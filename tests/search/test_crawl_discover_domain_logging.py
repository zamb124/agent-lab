"""Сбой discover_domain записывается в строку домена."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx2
import pytest

from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlProfile,
    CrawlProfileCreateRequest,
)
from core.search.index_models import SearchIndexDefinition


@pytest.mark.asyncio
async def test_discover_domain_records_sitemap_failure(
    search_di,
    unique_id: str,
) -> None:
    now = datetime.now(UTC)
    search_index_id = f"idx{unique_id}"[:64]
    profile_id = f"cr{unique_id}"[:64]
    _ = await SearchIndexDefinition.create(
        SearchIndexDefinition(
            search_index_id=search_index_id,
            company_id="system",
            display_name="Discover failure",
            rag_namespace_id=f"ns-{unique_id}",
            rag_collection_id=f"col-{unique_id}",
            created_at=now,
            updated_at=now,
        )
    )
    _ = await CrawlProfile.create(
        CrawlProfileCreateRequest(
            crawl_profile_id=profile_id,
            search_index_id=search_index_id,
            refresh_interval_seconds=21600,
        )
    )
    domain = await CrawlDomain.create(
        profile_id,
        CrawlDomainCreateRequest(domain=f"missing-{unique_id}.invalid"),
        next_crawl_after=now,
    )

    with pytest.raises(httpx2.ConnectError):
        await search_di.crawl_orchestrator_service.discover_domain(
            domain.crawl_domain_id,
            f"job-{unique_id}",
            profile_id,
        )

    stored = await CrawlDomain.get(domain.crawl_domain_id)
    assert stored is not None
    assert stored.status == "error"
    assert stored.last_error is not None
    assert stored.last_error != ""
    assert stored.next_crawl_after > now

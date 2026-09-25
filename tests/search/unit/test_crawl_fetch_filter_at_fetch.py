"""Fetch-time URL filter rejection in crawl orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import CrawlDomain, CrawlJob, CrawlProfile, CrawlProfileWithIndex, CrawlUrl
from core.search.index_models import SearchIndexDefinition

pytestmark = pytest.mark.unit


def _profile_bundle() -> CrawlProfileWithIndex:
    now = datetime.now(UTC)
    profile = CrawlProfile(
        crawl_profile_id="cr_test",
        search_index_id="runet",
        enabled=True,
        seed_source="manual",
        refresh_interval_seconds=21600,
        max_urls_per_domain_per_tick=10,
        max_domains_per_tick=10,
        max_urls_per_batch=10,
        http_concurrency=2,
        browser_fallback_enabled=True,
        sitemap_stale_after_seconds=86400,
        created_at=now,
        updated_at=now,
    )
    search_index = SearchIndexDefinition(
        search_index_id="runet",
        company_id="system",
        display_name="Runet",
        rag_namespace_id="runet:ns",
        rag_collection_id="runet",
        enabled=True,
        search_enabled=True,
        created_at=now,
        updated_at=now,
    )
    return CrawlProfileWithIndex(profile=profile, search_index=search_index)


@pytest.mark.asyncio
@pytest.mark.xfail(reason="URL filter check removed from fetch_one_url — filtering moved to sitemap parsing")
async def test_fetch_one_url_skips_filter_rejected_without_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    profile_bundle = _profile_bundle()
    domain = CrawlDomain(
        crawl_domain_id="dom-vk",
        crawl_profile_id="cr_test",
        domain="vkplay.ru",
        category="manual",
        status="active",
        exclude_url_patterns=[r"/play/game(/|$)"],
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )
    crawl_url = CrawlUrl(
        crawl_url_id="url-1",
        crawl_domain_id="dom-vk",
        url="https://vkplay.ru/play/game/demo",
        canonical_url="https://vkplay.ru/play/game/demo",
        crawl_status="fetching",
        fetch_attempts=0,
        created_at=now,
        updated_at=now,
    )

    fetch_service = AsyncMock()
    mark_skipped_mock = AsyncMock()
    increment_mock = AsyncMock()
    log_outcome = MagicMock()

    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlDomain, "get", AsyncMock(return_value=domain))
    monkeypatch.setattr(CrawlDomain, "mark_crawled", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "claim_pending_batch", AsyncMock(return_value=[crawl_url]))
    monkeypatch.setattr(CrawlUrl, "mark_skipped", mark_skipped_mock)
    monkeypatch.setattr(CrawlUrl, "mark_failed", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "get", AsyncMock(return_value=crawl_url))
    monkeypatch.setattr(CrawlUrl, "count_pending", AsyncMock(return_value=0))
    monkeypatch.setattr(CrawlUrl, "count_pending_for_profile", AsyncMock(return_value=0))
    monkeypatch.setattr(CrawlJob, "increment", increment_mock)

    orchestrator = CrawlOrchestratorService(
        fetch_service=fetch_service,
        page_enrichment_service=AsyncMock(),
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    with patch(
        "apps.search.services.crawl.orchestrator_service.log_crawl_url_outcome",
        log_outcome,
    ):
        await orchestrator.fetch_one_url("dom-vk", "job-1", "cr_test", 1)

    fetch_service.fetch_markdown.assert_not_called()
    mark_skipped_mock.assert_awaited_once_with("url-1", None)
    increment_mock.assert_awaited_once_with("job-1", urls_skipped=1)
    log_outcome.assert_called_once()
    assert log_outcome.call_args.kwargs["crawl_skip_reason"] == "filter_rejected"

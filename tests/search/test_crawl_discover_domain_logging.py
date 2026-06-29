"""Structured logging when discover_domain fails."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import CrawlDomain, CrawlProfile, CrawlProfileWithIndex
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig


@pytest.mark.asyncio
async def test_discover_domain_logs_structured_failure_on_generic_exception() -> None:
    now = datetime.now(UTC)
    profile = CrawlProfile(
        crawl_profile_id="cr_test",
        search_index_id="runet",
        enabled=True,
        seed_source="manual",
        refresh_interval_seconds=21600,
        max_urls_per_domain_per_tick=200,
        max_domains_per_tick=20,
        max_urls_per_batch=5,
        http_concurrency=3,
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
        retrieval=SearchIndexRetrievalConfig(),
        created_at=now,
        updated_at=now,
    )
    profile_bundle = CrawlProfileWithIndex(profile=profile, search_index=search_index)
    domain = CrawlDomain(
        crawl_domain_id="dom-1",
        crawl_profile_id="cr_test",
        domain="example.com",
        category="manual",
        status="active",
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )

    class _ProfileRepo:
        async def get_with_index(self, crawl_profile_id: str) -> CrawlProfileWithIndex:
            assert crawl_profile_id == "cr_test"
            return profile_bundle

    class _DomainRepo:
        async def get(self, crawl_domain_id: str) -> CrawlDomain:
            assert crawl_domain_id == "dom-1"
            return domain

        schedule_next = AsyncMock()

    domain_repo = _DomainRepo()

    orchestrator = CrawlOrchestratorService(
        crawl_profile_repository=_ProfileRepo(),  # pyright: ignore[reportArgumentType]
        crawl_domain_repository=domain_repo,  # pyright: ignore[reportArgumentType]
        crawl_url_repository=AsyncMock(),
        crawl_job_repository=AsyncMock(),
        fetch_service=AsyncMock(),
        page_enrichment_service=AsyncMock(),
        rag_client=AsyncMock(),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    discover_mock = AsyncMock(side_effect=RuntimeError("sitemap boom"))
    log_failed_mock = MagicMock()

    with (
        patch(
            "apps.search.services.crawl.orchestrator_service.discover_sitemap_urls",
            discover_mock,
        ),
        patch(
            "apps.search.services.crawl.orchestrator_service.log_crawl_discover_failed",
            log_failed_mock,
        ),
    ):
        with pytest.raises(RuntimeError, match="sitemap boom"):
            await orchestrator.discover_domain("dom-1", "job-1", "cr_test")

    discover_mock.assert_awaited_once()
    domain_repo.schedule_next.assert_awaited_once()
    log_failed_mock.assert_called_once()
    call_kwargs = log_failed_mock.call_args.kwargs
    assert call_kwargs["crawl_profile_id"] == "cr_test"
    assert call_kwargs["crawl_job_id"] == "job-1"
    assert call_kwargs["crawl_domain_id"] == "dom-1"
    assert call_kwargs["sitemap_error_kind"] == "RuntimeError"
    assert call_kwargs["exception_message"] == "sitemap boom"

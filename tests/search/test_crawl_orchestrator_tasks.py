"""Parallel crawl fetch enqueue."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.search.models import CrawlProfile, CrawlProfileWithIndex, CrawlUrl
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.taskiq_capture import taskiq_task_name


@pytest.mark.asyncio
async def test_enqueue_domain_fetch_respects_http_concurrency(
    monkeypatch: pytest.MonkeyPatch,
    search_di,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

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
        created_at=now,
        updated_at=now,
    )
    profile_bundle = CrawlProfileWithIndex(profile=profile, search_index=search_index)

    async def _require_with_index(crawl_profile_id: str) -> CrawlProfileWithIndex:
        assert crawl_profile_id == "cr_test"
        return profile_bundle

    async def _count_pending(crawl_domain_id: str) -> int:
        assert crawl_domain_id == "dom-1"
        return 10

    monkeypatch.setattr(CrawlProfile, "require_with_index", _require_with_index)
    monkeypatch.setattr(CrawlUrl, "count_pending", _count_pending)

    await search_di.crawl_orchestrator_service._enqueue_domain_fetch(
        crawl_domain_id="dom-1",
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        url_budget=10,
    )

    assert len(enqueued) == 3
    for task_name, domain_id, job_id, profile_id, url_budget in enqueued:
        assert task_name == "crawl_fetch_url"
        assert domain_id == "dom-1"
        assert job_id == "job-1"
        assert profile_id == "cr_test"
        assert url_budget == 1

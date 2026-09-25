"""Orchestrator backlog priority and fetch chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import CrawlDomain, CrawlJob, CrawlProfile, CrawlProfileWithIndex, CrawlUrl
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.taskiq_capture import taskiq_task_name


@pytest.fixture(autouse=True)
def _fake_crawl_job_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тесты подменяют CrawlJob.start фейком job-1: счётчик в БД не пишется."""
    monkeypatch.setattr(CrawlJob, "increment", AsyncMock())


def _profile_bundle(*, max_domains_per_tick: int = 2) -> CrawlProfileWithIndex:
    now = datetime.now(UTC)
    profile = CrawlProfile(
        crawl_profile_id="cr_test",
        search_index_id="runet",
        enabled=True,
        seed_source="manual",
        refresh_interval_seconds=21600,
        max_urls_per_domain_per_tick=10,
        max_domains_per_tick=max_domains_per_tick,
        max_urls_per_batch=5,
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


def _domain(domain_id: str, domain_name: str) -> CrawlDomain:
    now = datetime.now(UTC)
    return CrawlDomain(
        crawl_domain_id=domain_id,
        crawl_profile_id="cr_test",
        domain=domain_name,
        category="unknown",
        status="active",
        next_crawl_after=now + timedelta(hours=6),
        created_at=now,
        updated_at=now,
    )


def _orchestrator() -> CrawlOrchestratorService:
    return CrawlOrchestratorService(
        fetch_service=AsyncMock(),
        page_enrichment_service=AsyncMock(),
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(create_namespace=AsyncMock()),
        crawl_config=get_search_settings().crawl,
    )


@pytest.mark.asyncio
async def test_run_tick_prioritizes_backlog_over_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

    profile_bundle = _profile_bundle(max_domains_per_tick=2)
    backlog_domain = _domain("dom-backlog", "dzen.ru")
    due_domain = _domain("dom-due", "example.com")
    due_domain = due_domain.model_copy(update={"next_crawl_after": datetime.now(UTC) - timedelta(minutes=1)})

    async def list_with_pending_urls(crawl_profile_id: str, *, limit: int) -> list[CrawlDomain]:
        assert crawl_profile_id == "cr_test"
        assert limit == 2
        return [backlog_domain]

    async def list_due(crawl_profile_id: str, *, now: datetime, limit: int) -> list[CrawlDomain]:
        assert limit == 1
        return [due_domain]

    async def count_pending(crawl_domain_id: str) -> int:
        if crawl_domain_id == "dom-backlog":
            return 100
        return 0

    job = CrawlJob(
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        trigger="manual",
        status="running",
        started_at=datetime.now(UTC),
    )
    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlDomain, "list_with_pending_urls", list_with_pending_urls)
    monkeypatch.setattr(CrawlDomain, "list_due", list_due)
    monkeypatch.setattr(CrawlDomain, "schedule_next", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "count_pending", count_pending)
    monkeypatch.setattr(CrawlUrl, "count_pending_for_profile", AsyncMock(return_value=100))
    monkeypatch.setattr(CrawlUrl, "domain_change_stats", AsyncMock(return_value=(0, 0)))
    monkeypatch.setattr(CrawlJob, "start", AsyncMock(return_value=job))
    monkeypatch.setattr(CrawlJob, "finish", AsyncMock())

    orchestrator = _orchestrator()
    result = await orchestrator.run_tick(
        crawl_profile_id="cr_test",
        trigger="manual",
        schedule_task_id=None,
    )

    fetch_tasks = [item for item in enqueued if item[0] == "crawl_fetch_url"]
    discover_tasks = [item for item in enqueued if item[0] == "crawl_discover_domain"]
    orchestrator_ticks = [item for item in enqueued if item[0] == "crawl_orchestrator_tick"]

    assert result["domains_scheduled"] == 2
    assert len(fetch_tasks) == 2
    assert fetch_tasks[0][1] == "dom-backlog"
    assert len(discover_tasks) == 1
    assert discover_tasks[0][1] == "dom-due"
    assert orchestrator_ticks == []


@pytest.mark.asyncio
async def test_fetch_one_url_reenqueues_while_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

    profile_bundle = _profile_bundle()
    domain = _domain("dom-1", "example.com")
    now = datetime.now(UTC)

    async def claim_pending_batch(crawl_domain_id: str, limit: int) -> list[CrawlUrl]:
        return [
            CrawlUrl(
                crawl_url_id="url-1",
                crawl_domain_id=crawl_domain_id,
                url="https://example.com/page",
                canonical_url="https://example.com/page",
                crawl_status="fetching",
                created_at=now,
                updated_at=now,
            )
        ]

    async def mark_crawled(crawl_domain_id: str, crawled_at: datetime) -> None:
        raise AssertionError("mark_crawled must not run while pending remains")

    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlDomain, "get", AsyncMock(return_value=domain))
    monkeypatch.setattr(CrawlDomain, "mark_crawled", mark_crawled)
    monkeypatch.setattr(CrawlUrl, "claim_pending_batch", claim_pending_batch)
    monkeypatch.setattr(CrawlUrl, "count_pending", AsyncMock(return_value=4))

    orchestrator = _orchestrator()
    orchestrator._fetch_and_index_url = AsyncMock()  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator.fetch_one_url("dom-1", "job-1", "cr_test", url_budget=1)

    fetch_tasks = [item for item in enqueued if item[0] == "crawl_fetch_url"]
    assert len(fetch_tasks) == 1
    assert fetch_tasks[0][-1] == 1


@pytest.mark.asyncio
async def test_fetch_one_url_enqueues_tick_when_domain_drained_but_profile_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

    profile_bundle = _profile_bundle()
    domain = _domain("dom-1", "example.com")
    now = datetime.now(UTC)

    async def claim_pending_batch(crawl_domain_id: str, limit: int) -> list[CrawlUrl]:
        return [
            CrawlUrl(
                crawl_url_id="url-1",
                crawl_domain_id=crawl_domain_id,
                url="https://example.com/page",
                canonical_url="https://example.com/page",
                crawl_status="fetching",
                created_at=now,
                updated_at=now,
            )
        ]

    async def count_pending_for_profile(crawl_profile_id: str) -> int:
        assert crawl_profile_id == "cr_test"
        return 50

    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlDomain, "get", AsyncMock(return_value=domain))
    monkeypatch.setattr(CrawlDomain, "mark_crawled", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "claim_pending_batch", claim_pending_batch)
    monkeypatch.setattr(CrawlUrl, "count_pending", AsyncMock(return_value=0))
    monkeypatch.setattr(CrawlUrl, "count_pending_for_profile", count_pending_for_profile)

    orchestrator = _orchestrator()
    orchestrator._fetch_and_index_url = AsyncMock()  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator.fetch_one_url("dom-1", "job-1", "cr_test", url_budget=1)

    fetch_tasks = [item for item in enqueued if item[0] == "crawl_fetch_url"]
    orchestrator_ticks = [item for item in enqueued if item[0] == "crawl_orchestrator_tick"]
    assert fetch_tasks == []
    assert orchestrator_ticks == [("crawl_orchestrator_tick", "cr_test")]


@pytest.mark.asyncio
async def test_run_tick_does_not_reenqueue_when_no_domains_scheduled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

    profile_bundle = _profile_bundle(max_domains_per_tick=1)
    job = CrawlJob(
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        trigger="manual",
        status="running",
        started_at=datetime.now(UTC),
    )
    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlDomain, "list_with_pending_urls", AsyncMock(return_value=[]))
    monkeypatch.setattr(CrawlDomain, "list_due", AsyncMock(return_value=[]))
    monkeypatch.setattr(CrawlUrl, "count_pending_for_profile", AsyncMock(return_value=10))
    monkeypatch.setattr(CrawlJob, "start", AsyncMock(return_value=job))
    monkeypatch.setattr(CrawlJob, "finish", AsyncMock())
    monkeypatch.setattr(CrawlJob, "increment", AsyncMock())

    orchestrator = _orchestrator()
    result = await orchestrator.run_tick(
        crawl_profile_id="cr_test",
        trigger="manual",
        schedule_task_id=None,
    )

    orchestrator_ticks = [item for item in enqueued if item[0] == "crawl_orchestrator_tick"]
    assert result["domains_scheduled"] == 0
    assert orchestrator_ticks == []


@pytest.mark.asyncio
async def test_run_tick_creates_rag_namespace_once_per_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    profile_bundle = _profile_bundle(max_domains_per_tick=1)
    job = CrawlJob(
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        trigger="manual",
        status="running",
        started_at=datetime.now(UTC),
    )
    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlDomain, "list_with_pending_urls", AsyncMock(return_value=[]))
    monkeypatch.setattr(CrawlDomain, "list_due", AsyncMock(return_value=[]))
    monkeypatch.setattr(CrawlUrl, "count_pending_for_profile", AsyncMock(return_value=0))
    monkeypatch.setattr(CrawlJob, "start", AsyncMock(return_value=job))
    monkeypatch.setattr(CrawlJob, "finish", AsyncMock())

    orchestrator = _orchestrator()
    await orchestrator.run_tick(
        crawl_profile_id="cr_test",
        trigger="manual",
        schedule_task_id=None,
    )
    await orchestrator.run_tick(
        crawl_profile_id="cr_test",
        trigger="manual",
        schedule_task_id=None,
    )

    orchestrator._rag_client.create_namespace.assert_awaited_once()  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_fetch_and_index_url_enqueues_enrich_when_llm_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

    now = datetime.now(UTC)
    profile_bundle = _profile_bundle()
    profile_bundle = profile_bundle.model_copy(
        update={
            "profile": profile_bundle.profile.model_copy(
                update={"llm_enrichment_enabled": True},
            ),
        },
    )
    domain = _domain("dom-1", "example.com")
    crawl_url = CrawlUrl(
        crawl_url_id="url-1",
        crawl_domain_id="dom-1",
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        crawl_status="fetching",
        created_at=now,
        updated_at=now,
    )

    from core.crawl.models import CrawlFetchResult

    fetched = CrawlFetchResult(
        url=crawl_url.url,
        canonical_url=crawl_url.canonical_url,
        markdown="# Example\n\nBody text for indexing.",
        title="Example",
        content_hash="hash-layer1",
        fetch_transport="http",
    )

    monkeypatch.setattr(CrawlUrl, "mark_indexed", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "mark_failed", AsyncMock())

    orchestrator = _orchestrator()
    orchestrator._fetch_service.fetch_markdown = AsyncMock(return_value=fetched)  # pyright: ignore[reportAttributeAccessIssue]
    orchestrator._ingest_service.ingest_page = AsyncMock(return_value="doc-1")  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator._fetch_and_index_url(
        crawl_url=crawl_url,
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        profile_bundle=profile_bundle,
        domain=domain,
        stored_extract_hash=None,
    )

    enrich_tasks = [item for item in enqueued if item[0] == "crawl_enrich_url"]
    assert len(enrich_tasks) == 1
    assert enrich_tasks[0][1:] == ("url-1", "job-1", "cr_test")
    orchestrator._page_enrichment_service.enrich_page.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

"""Orchestrator backlog priority and fetch chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import CrawlDomain, CrawlJob, CrawlProfile, CrawlProfileWithIndex, CrawlUrl
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig


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
        retrieval=SearchIndexRetrievalConfig(),
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


def _orchestrator(
    *,
    profile_bundle: CrawlProfileWithIndex,
    domain_repo: object,
    url_repo: object,
    job_repo: object,
) -> CrawlOrchestratorService:
    return CrawlOrchestratorService(
        crawl_profile_repository=AsyncMock(get_with_index=AsyncMock(return_value=profile_bundle)),
        crawl_domain_repository=domain_repo,  # pyright: ignore[reportArgumentType]
        crawl_url_repository=url_repo,  # pyright: ignore[reportArgumentType]
        crawl_job_repository=job_repo,  # pyright: ignore[reportArgumentType]
        fetch_service=AsyncMock(),
        page_enrichment_service=AsyncMock(),
        rag_client=AsyncMock(create_namespace=AsyncMock()),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )


@pytest.mark.asyncio
async def test_run_tick_prioritizes_backlog_over_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle(max_domains_per_tick=2)
    backlog_domain = _domain("dom-backlog", "dzen.ru")
    due_domain = _domain("dom-due", "example.com")
    due_domain = due_domain.model_copy(update={"next_crawl_after": datetime.now(UTC) - timedelta(minutes=1)})

    class _DomainRepo:
        async def list_with_pending_urls(self, crawl_profile_id: str, *, limit: int) -> list[CrawlDomain]:
            assert crawl_profile_id == "cr_test"
            assert limit == 2
            return [backlog_domain]

        async def list_due(self, crawl_profile_id: str, *, now: datetime, limit: int) -> list[CrawlDomain]:
            assert limit == 1
            return [due_domain]

        async def schedule_next(self, crawl_domain_id: str, next_crawl_after: datetime, **kwargs: object) -> None:
            pass

    class _UrlRepo:
        async def count_pending(self, crawl_domain_id: str) -> int:
            if crawl_domain_id == "dom-backlog":
                return 100
            return 0

        async def count_pending_for_profile(self, crawl_profile_id: str) -> int:
            return 100

    job = CrawlJob(
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        trigger="manual",
        status="running",
        started_at=datetime.now(UTC),
    )
    job_repo = AsyncMock()
    job_repo.start = AsyncMock(return_value=job)
    job_repo.increment = AsyncMock()
    job_repo.finish = AsyncMock()

    orchestrator = _orchestrator(
        profile_bundle=profile_bundle,
        domain_repo=_DomainRepo(),
        url_repo=_UrlRepo(),
        job_repo=job_repo,
    )

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
    assert len(orchestrator_ticks) == 1


@pytest.mark.asyncio
async def test_fetch_one_url_reenqueues_while_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle()
    domain = _domain("dom-1", "example.com")
    now = datetime.now(UTC)

    class _UrlRepo:
        async def claim_pending_batch(self, crawl_domain_id: str, limit: int) -> list[object]:
            from core.crawl.models import CrawlUrl

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

        async def count_pending(self, crawl_domain_id: str) -> int:
            return 4

    class _DomainRepo:
        async def get(self, crawl_domain_id: str) -> CrawlDomain:
            return domain

        async def mark_crawled(self, crawl_domain_id: str, crawled_at: datetime) -> None:
            raise AssertionError("mark_crawled must not run while pending remains")

    job_repo = AsyncMock()
    job_repo.increment = AsyncMock()

    orchestrator = _orchestrator(
        profile_bundle=profile_bundle,
        domain_repo=_DomainRepo(),
        url_repo=_UrlRepo(),
        job_repo=job_repo,
    )
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

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle()
    domain = _domain("dom-1", "example.com")
    now = datetime.now(UTC)

    class _UrlRepo:
        async def claim_pending_batch(self, crawl_domain_id: str, limit: int) -> list[object]:
            from core.crawl.models import CrawlUrl

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

        async def count_pending(self, crawl_domain_id: str) -> int:
            return 0

        async def count_pending_for_profile(self, crawl_profile_id: str) -> int:
            assert crawl_profile_id == "cr_test"
            return 50

    class _DomainRepo:
        async def get(self, crawl_domain_id: str) -> CrawlDomain:
            return domain

        async def mark_crawled(self, crawl_domain_id: str, crawled_at: datetime) -> None:
            assert crawl_domain_id == "dom-1"

    job_repo = AsyncMock()
    job_repo.increment = AsyncMock()

    orchestrator = _orchestrator(
        profile_bundle=profile_bundle,
        domain_repo=_DomainRepo(),
        url_repo=_UrlRepo(),
        job_repo=job_repo,
    )
    orchestrator._fetch_and_index_url = AsyncMock()  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator.fetch_one_url("dom-1", "job-1", "cr_test", url_budget=1)

    fetch_tasks = [item for item in enqueued if item[0] == "crawl_fetch_url"]
    orchestrator_ticks = [item for item in enqueued if item[0] == "crawl_orchestrator_tick"]
    assert fetch_tasks == []
    assert orchestrator_ticks == [("crawl_orchestrator_tick", "cr_test")]


@pytest.mark.asyncio
async def test_run_tick_reenqueues_while_profile_pending_even_without_new_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle(max_domains_per_tick=1)

    class _DomainRepo:
        async def list_with_pending_urls(self, crawl_profile_id: str, *, limit: int) -> list[CrawlDomain]:
            return []

        async def list_due(self, crawl_profile_id: str, *, now: datetime, limit: int) -> list[CrawlDomain]:
            return []

    class _UrlRepo:
        async def count_pending_for_profile(self, crawl_profile_id: str) -> int:
            return 10

    job = CrawlJob(
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        trigger="manual",
        status="running",
        started_at=datetime.now(UTC),
    )
    job_repo = AsyncMock()
    job_repo.start = AsyncMock(return_value=job)
    job_repo.finish = AsyncMock()

    orchestrator = _orchestrator(
        profile_bundle=profile_bundle,
        domain_repo=_DomainRepo(),
        url_repo=_UrlRepo(),
        job_repo=job_repo,
    )

    await orchestrator.run_tick(
        crawl_profile_id="cr_test",
        trigger="manual",
        schedule_task_id=None,
    )

    orchestrator_ticks = [item for item in enqueued if item[0] == "crawl_orchestrator_tick"]
    assert orchestrator_ticks == [("crawl_orchestrator_tick", "cr_test")]


@pytest.mark.asyncio
async def test_fetch_and_index_url_enqueues_enrich_when_llm_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
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

    orchestrator = _orchestrator(
        profile_bundle=profile_bundle,
        domain_repo=AsyncMock(get=AsyncMock(return_value=domain)),
        url_repo=AsyncMock(
            mark_indexed=AsyncMock(),
            mark_failed=AsyncMock(),
        ),
        job_repo=AsyncMock(increment=AsyncMock()),
    )
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

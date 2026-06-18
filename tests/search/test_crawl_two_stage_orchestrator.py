"""Unit tests for two-stage crawl orchestrator contract."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import (
    CrawlDomain,
    CrawlEnrichedChunk,
    CrawlEnrichedPage,
    CrawlFetchResult,
    CrawlProfile,
    CrawlProfileWithIndex,
    CrawlUrl,
)
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig

pytestmark = pytest.mark.unit


def _profile_bundle(*, llm_enrichment_enabled: bool = True) -> CrawlProfileWithIndex:
    now = datetime.now(UTC)
    profile = CrawlProfile(
        crawl_profile_id="cr_test",
        search_index_id="runet",
        enabled=True,
        seed_source="manual",
        refresh_interval_seconds=21600,
        max_urls_per_domain_per_tick=10,
        max_domains_per_tick=2,
        max_urls_per_batch=5,
        http_concurrency=2,
        browser_fallback_enabled=True,
        sitemap_stale_after_seconds=86400,
        llm_enrichment_enabled=llm_enrichment_enabled,
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


def _domain() -> CrawlDomain:
    now = datetime.now(UTC)
    return CrawlDomain(
        crawl_domain_id="dom-1",
        crawl_profile_id="cr_test",
        domain="example.com",
        category="unknown",
        crawl_policy="allow",
        status="active",
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )


def _crawl_url(*, crawl_status: str = "fetching", document_id: str | None = None) -> CrawlUrl:
    now = datetime.now(UTC)
    return CrawlUrl(
        crawl_url_id="url-1",
        crawl_domain_id="dom-1",
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        crawl_status=crawl_status,  # pyright: ignore[reportArgumentType]
        document_id=document_id,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_fetch_layer1_never_calls_enrichment_synchronously(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)
    fetched = CrawlFetchResult(
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        markdown="# Example\n\nRaw markdown body for layer one indexing.",
        title="Example",
        content_hash="hash-layer1",
        fetch_transport="http",
    )
    page_enrichment_service = AsyncMock()
    orchestrator = CrawlOrchestratorService(
        crawl_profile_repository=AsyncMock(get_with_index=AsyncMock(return_value=profile_bundle)),
        crawl_domain_repository=AsyncMock(get=AsyncMock(return_value=_domain())),
        crawl_url_repository=AsyncMock(
            mark_indexed=AsyncMock(),
            mark_failed=AsyncMock(),
        ),
        crawl_job_repository=AsyncMock(increment=AsyncMock()),
        fetch_service=AsyncMock(fetch_markdown=AsyncMock(return_value=fetched)),
        page_enrichment_service=page_enrichment_service,
        rag_client=AsyncMock(),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )
    orchestrator._ingest_service.ingest_page = AsyncMock(return_value="doc-1")  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator._fetch_and_index_url(
        crawl_url=_crawl_url(),
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        profile_bundle=profile_bundle,
        domain=_domain(),
        stored_extract_hash=None,
    )

    page_enrichment_service.enrich_page.assert_not_called()
    page_enrichment_service.enrich_markdown.assert_not_called()
    enrich_tasks = [item for item in enqueued if item[0] == "crawl_enrich_url"]
    assert len(enrich_tasks) == 1


@pytest.mark.asyncio
async def test_fetch_layer1_skips_enrich_kiq_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle(llm_enrichment_enabled=False)
    fetched = CrawlFetchResult(
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        markdown="# Example\n\nRaw markdown.",
        title="Example",
        content_hash="hash-layer1",
        fetch_transport="http",
    )
    orchestrator = CrawlOrchestratorService(
        crawl_profile_repository=AsyncMock(get_with_index=AsyncMock(return_value=profile_bundle)),
        crawl_domain_repository=AsyncMock(get=AsyncMock(return_value=_domain())),
        crawl_url_repository=AsyncMock(mark_indexed=AsyncMock(), mark_failed=AsyncMock()),
        crawl_job_repository=AsyncMock(increment=AsyncMock()),
        fetch_service=AsyncMock(fetch_markdown=AsyncMock(return_value=fetched)),
        page_enrichment_service=AsyncMock(),
        rag_client=AsyncMock(),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )
    orchestrator._ingest_service.ingest_page = AsyncMock(return_value="doc-1")  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator._fetch_and_index_url(
        crawl_url=_crawl_url(),
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        profile_bundle=profile_bundle,
        domain=_domain(),
        stored_extract_hash=None,
    )

    enrich_tasks = [item for item in enqueued if item[0] == "crawl_enrich_url"]
    assert enrich_tasks == []


@pytest.mark.asyncio
async def test_enrich_one_url_reads_snapshot_not_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)
    enriched_page = CrawlEnrichedPage(
        page_summary="Summary",
        chunks=[
            CrawlEnrichedChunk(
                content="Chunk",
                metadata_summary="Meta",
                hierarchy=["H1"],
            )
        ],
        enrichment_model="test-model",
        enrichment_prompt_version="v1",
    )

    class _UrlRepo:
        async def get(self, crawl_url_id: str) -> CrawlUrl:
            assert crawl_url_id == "url-1"
            return CrawlUrl(
                crawl_url_id="url-1",
                crawl_domain_id="dom-1",
                url="https://example.com/page",
                canonical_url="https://example.com/page",
                crawl_status="indexed",
                document_id="doc-1",
                extract_content_hash="hash-layer1",
                fetch_transport="http",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        async def get_layer1_snapshot(self, crawl_url_id: str) -> tuple[str, str, str, str, str]:
            assert crawl_url_id == "url-1"
            return (
                "https://example.com/page",
                "https://example.com/page",
                "# Stored\n\nFrom database snapshot.",
                "Stored title",
                "hash-layer1",
            )

        async def mark_enriched(self, crawl_url_id: str, **kwargs: object) -> None:
            assert crawl_url_id == "url-1"

        async def mark_enrichment_failed(self, crawl_url_id: str, error: str) -> None:
            raise AssertionError("mark_enrichment_failed must not run on success")

    fetch_service = AsyncMock()
    page_enrichment_service = AsyncMock(enrich_markdown=AsyncMock(return_value=enriched_page))

    from collections.abc import AsyncGenerator
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop_enrichment_lock() -> AsyncGenerator[None]:
        yield

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.crawl_enrichment_lock",
        _noop_enrichment_lock,
    )

    orchestrator = CrawlOrchestratorService(
        crawl_profile_repository=AsyncMock(get_with_index=AsyncMock(return_value=profile_bundle)),
        crawl_domain_repository=AsyncMock(get=AsyncMock(return_value=_domain())),
        crawl_url_repository=_UrlRepo(),  # pyright: ignore[reportArgumentType]
        crawl_job_repository=AsyncMock(increment=AsyncMock()),
        fetch_service=fetch_service,
        page_enrichment_service=page_enrichment_service,
        rag_client=AsyncMock(),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )
    orchestrator._ingest_service.reingest_enriched_page = AsyncMock(return_value="doc-1")  # pyright: ignore[reportAttributeAccessIssue]

    await orchestrator.enrich_one_url("url-1", "job-1", "cr_test")

    fetch_service.fetch_markdown.assert_not_called()
    page_enrichment_service.enrich_markdown.assert_awaited_once()
    enrich_call = page_enrichment_service.enrich_markdown.await_args
    assert enrich_call is not None
    assert "From database snapshot." in enrich_call.kwargs["markdown"]


@pytest.mark.asyncio
async def test_enrich_failure_keeps_indexed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)
    enrichment_failed_mock = AsyncMock()
    mark_failed_mock = AsyncMock()

    class _UrlRepo:
        async def get(self, crawl_url_id: str) -> CrawlUrl:
            return CrawlUrl(
                crawl_url_id="url-1",
                crawl_domain_id="dom-1",
                url="https://example.com/page",
                canonical_url="https://example.com/page",
                crawl_status="indexed",
                document_id="doc-1",
                extract_content_hash="hash-layer1",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        async def get_layer1_snapshot(self, crawl_url_id: str) -> tuple[str, str, str, str, str]:
            return (
                "https://example.com/page",
                "https://example.com/page",
                "markdown",
                "title",
                "hash-layer1",
            )

        async def mark_enrichment_failed(self, crawl_url_id: str, error: str) -> None:
            await enrichment_failed_mock(crawl_url_id, error)

        async def mark_failed(self, crawl_url_id: str, error: str) -> None:
            await mark_failed_mock(crawl_url_id, error)

        async def mark_enriched(self, crawl_url_id: str, **kwargs: object) -> None:
            raise AssertionError("mark_enriched must not run on failure")

    from collections.abc import AsyncGenerator
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop_enrichment_lock() -> AsyncGenerator[None]:
        yield

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.crawl_enrichment_lock",
        _noop_enrichment_lock,
    )

    page_enrichment_service = AsyncMock(
        enrich_markdown=AsyncMock(side_effect=ValueError("litserve timeout")),
    )

    orchestrator = CrawlOrchestratorService(
        crawl_profile_repository=AsyncMock(get_with_index=AsyncMock(return_value=profile_bundle)),
        crawl_domain_repository=AsyncMock(get=AsyncMock(return_value=_domain())),
        crawl_url_repository=_UrlRepo(),  # pyright: ignore[reportArgumentType]
        crawl_job_repository=AsyncMock(increment=AsyncMock()),
        fetch_service=AsyncMock(),
        page_enrichment_service=page_enrichment_service,
        rag_client=AsyncMock(),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    with pytest.raises(ValueError, match="litserve timeout"):
        await orchestrator.enrich_one_url("url-1", "job-1", "cr_test")

    enrichment_failed_mock.assert_awaited_once()
    mark_failed_mock.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_enrichment_backfill_kiqs_missing_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)

    class _UrlRepo:
        async def list_indexed_missing_enrichment(
            self,
            crawl_profile_id: str,
            *,
            limit: int,
        ) -> list[str]:
            assert crawl_profile_id == "cr_test"
            assert limit == 100
            return ["url-a", "url-b"]

    orchestrator = CrawlOrchestratorService(
        crawl_profile_repository=AsyncMock(get_with_index=AsyncMock(return_value=profile_bundle)),
        crawl_domain_repository=AsyncMock(),
        crawl_url_repository=_UrlRepo(),  # pyright: ignore[reportArgumentType]
        crawl_job_repository=AsyncMock(),
        fetch_service=AsyncMock(),
        page_enrichment_service=AsyncMock(),
        rag_client=AsyncMock(),
        build_system_context=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    count = await orchestrator.enqueue_enrichment_backfill("cr_test", "job-backfill", limit=100)
    assert count == 2
    enrich_tasks = [item for item in enqueued if item[0] == "crawl_enrich_url"]
    assert enrich_tasks == [
        ("crawl_enrich_url", "url-a", "job-backfill", "cr_test"),
        ("crawl_enrich_url", "url-b", "job-backfill", "cr_test"),
    ]

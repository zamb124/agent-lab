"""Unit tests for two-stage crawl orchestrator contract."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from apps.search.config import get_search_settings
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import (
    CrawlDomain,
    CrawlFetchResult,
    CrawlJob,
    CrawlProfile,
    CrawlProfileWithIndex,
    CrawlStructuralSignals,
    CrawlUrl,
)
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.taskiq_capture import taskiq_task_name
from tests.search.unit.crawl_enrichment_fixtures import sample_enriched_page

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

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
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
    monkeypatch.setattr(CrawlUrl, "mark_indexed", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "mark_failed", AsyncMock())
    monkeypatch.setattr(CrawlJob, "increment", AsyncMock())
    orchestrator = CrawlOrchestratorService(
        fetch_service=AsyncMock(fetch_markdown=AsyncMock(return_value=fetched)),
        page_enrichment_service=page_enrichment_service,
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
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

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
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
    monkeypatch.setattr(CrawlUrl, "mark_indexed", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "mark_failed", AsyncMock())
    monkeypatch.setattr(CrawlJob, "increment", AsyncMock())
    orchestrator = CrawlOrchestratorService(
        fetch_service=AsyncMock(fetch_markdown=AsyncMock(return_value=fetched)),
        page_enrichment_service=AsyncMock(),
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
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
async def test_fetch_marks_skipped_on_extract_too_short(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.crawl.errors import CrawlExtractTooShortError

    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)
    mark_skipped_mock = AsyncMock()
    mark_failed_mock = AsyncMock()
    increment_mock = AsyncMock()
    monkeypatch.setattr(CrawlUrl, "mark_skipped", mark_skipped_mock)
    monkeypatch.setattr(CrawlUrl, "mark_failed", mark_failed_mock)
    monkeypatch.setattr(CrawlJob, "increment", increment_mock)
    orchestrator = CrawlOrchestratorService(
        fetch_service=AsyncMock(
            fetch_markdown=AsyncMock(
                side_effect=CrawlExtractTooShortError("https://example.com/thin"),
            ),
        ),
        page_enrichment_service=AsyncMock(),
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    await orchestrator._fetch_and_index_url(
        crawl_url=_crawl_url(),
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        profile_bundle=profile_bundle,
        domain=_domain(),
        stored_extract_hash=None,
    )

    mark_skipped_mock.assert_awaited_once_with("url-1", None)
    mark_failed_mock.assert_not_called()
    increment_mock.assert_awaited_once_with("job-1", urls_skipped=1)


@pytest.mark.asyncio
async def test_enrich_one_url_reads_snapshot_not_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)
    enriched_page = sample_enriched_page(
        enrichment_model="test-model",
        enrichment_prompt_version="structured",
    )

    indexed_url = CrawlUrl(
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

    async def get_layer1_snapshot(crawl_url_id: str) -> tuple[str, str, str, str, str, CrawlStructuralSignals]:
        assert crawl_url_id == "url-1"
        return (
            "https://example.com/page",
            "https://example.com/page",
            "# Stored\n\nFrom database snapshot.",
            "Stored title",
            "hash-layer1",
            CrawlStructuralSignals(title="Stored title"),
        )

    async def mark_enrichment_failed(crawl_url_id: str, error: str) -> None:
        raise AssertionError("mark_enrichment_failed must not run on success")

    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlUrl, "get", AsyncMock(return_value=indexed_url))
    monkeypatch.setattr(CrawlUrl, "get_layer1_snapshot", get_layer1_snapshot)
    monkeypatch.setattr(CrawlUrl, "mark_enriched", AsyncMock())
    monkeypatch.setattr(CrawlUrl, "mark_enrichment_failed", mark_enrichment_failed)
    monkeypatch.setattr(CrawlDomain, "get", AsyncMock(return_value=_domain()))
    monkeypatch.setattr(CrawlJob, "increment", AsyncMock())

    fetch_service = AsyncMock()
    page_enrichment_service = AsyncMock(enrich_markdown=AsyncMock(return_value=enriched_page))

    orchestrator = CrawlOrchestratorService(
        fetch_service=fetch_service,
        page_enrichment_service=page_enrichment_service,
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
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
    indexed_url = CrawlUrl(
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

    async def get_layer1_snapshot(crawl_url_id: str) -> tuple[str, str, str, str, str, CrawlStructuralSignals]:
        return (
            "https://example.com/page",
            "https://example.com/page",
            "markdown",
            "title",
            "hash-layer1",
            CrawlStructuralSignals(),
        )

    async def mark_enriched(crawl_url_id: str, **kwargs: object) -> None:
        raise AssertionError("mark_enriched must not run on failure")

    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlUrl, "get", AsyncMock(return_value=indexed_url))
    monkeypatch.setattr(CrawlUrl, "get_layer1_snapshot", get_layer1_snapshot)
    monkeypatch.setattr(CrawlUrl, "mark_enrichment_failed", enrichment_failed_mock)
    monkeypatch.setattr(CrawlUrl, "mark_failed", mark_failed_mock)
    monkeypatch.setattr(CrawlUrl, "mark_enriched", mark_enriched)
    monkeypatch.setattr(CrawlDomain, "get", AsyncMock(return_value=_domain()))
    monkeypatch.setattr(CrawlJob, "increment", AsyncMock())

    page_enrichment_service = AsyncMock(
        enrich_markdown=AsyncMock(side_effect=ValueError("humanitec_llm timeout")),
    )

    orchestrator = CrawlOrchestratorService(
        fetch_service=AsyncMock(),
        page_enrichment_service=page_enrichment_service,
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    with pytest.raises(ValueError, match="humanitec_llm timeout"):
        await orchestrator.enrich_one_url("url-1", "job-1", "cr_test")

    enrichment_failed_mock.assert_awaited_once()
    mark_failed_mock.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_enrichment_backfill_enqueues_missing_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[object, ...]] = []

    async def _capture(task: object, *args: object, **kwargs: object) -> None:
        enqueued.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service.enqueue",
        _capture,
    )

    profile_bundle = _profile_bundle(llm_enrichment_enabled=True)

    async def list_indexed_missing_enrichment(
        crawl_profile_id: str,
        *,
        limit: int,
    ) -> list[str]:
        assert crawl_profile_id == "cr_test"
        assert limit == 100
        return ["url-a", "url-b"]

    monkeypatch.setattr(CrawlProfile, "get_with_index", AsyncMock(return_value=profile_bundle))
    monkeypatch.setattr(CrawlUrl, "list_indexed_missing_enrichment", list_indexed_missing_enrichment)

    orchestrator = CrawlOrchestratorService(
        fetch_service=AsyncMock(),
        page_enrichment_service=AsyncMock(),
        politeness_service=AsyncMock(
            is_url_allowed=AsyncMock(return_value=True),
            wait_for_fetch_slot=AsyncMock(return_value=0.0),
        ),
        rag_client=AsyncMock(),
        crawl_config=get_search_settings().crawl,
    )

    count = await orchestrator.enqueue_enrichment_backfill("cr_test", "job-backfill", limit=100)
    assert count == 2
    enrich_tasks = [item for item in enqueued if item[0] == "crawl_enrich_url"]
    assert enrich_tasks == [
        ("crawl_enrich_url", "url-a", "job-backfill", "cr_test"),
        ("crawl_enrich_url", "url-b", "job-backfill", "cr_test"),
    ]

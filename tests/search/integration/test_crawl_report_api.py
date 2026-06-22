"""Crawl report REST API integration tests (real Postgres, HTTP, no mocks)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.search_worker.tasks.task_names import CRAWL_DISCOVER_DOMAIN_TASK_NAME
from core.crawl.models import (
    CrawlDomainSeed,
    CrawlProfileCreateRequest,
    CrawlStructuralSignals,
    SitemapEntry,
)
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(60, func_only=True)


async def _create_profile(search_container, unique_id: str) -> str:
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Crawl report {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_container.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            browser_fallback_enabled=False,
        )
    )
    return crawl_profile_id


def _count_map(items: list[dict]) -> dict[str, int]:
    return {item["status"]: item["count"] for item in items}


@pytest.mark.asyncio
async def test_crawl_profile_summary_empty(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)

    response = await search_client.get(f"/search/api/v1/crawl/profiles/{crawl_profile_id}/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["profile"]["crawl_profile_id"] == crawl_profile_id
    assert payload["domains_total"] == 0
    assert payload["domains_due"] == 0
    assert payload["domain_counts"] == []
    assert payload["url_counts"] == []
    assert payload["latest_job"] is None
    assert payload["running_job"] is None


@pytest.mark.asyncio
async def test_crawl_profile_summary_mixed_state(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)

    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [
            CrawlDomainSeed(domain="active.example.com", category="news", domain_rank=1),
            CrawlDomainSeed(domain="error.example.com", category="news", domain_rank=2),
        ],
        next_crawl_after=past,
    )
    domains_page = await search_container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=10,
        offset=0,
    )
    error_domain = next(item for item in domains_page.items if item.domain == "error.example.com")
    await search_container.crawl_domain_repository.schedule_next(
        error_domain.crawl_domain_id,
        next_crawl_after=past,
        last_error="robots blocked",
        status="error",
    )
    active_domain = next(item for item in domains_page.items if item.domain == "active.example.com")

    await search_container.crawl_url_repository.upsert_from_sitemap(
        active_domain.crawl_domain_id,
        [
            SitemapEntry(url="https://active.example.com/page-pending"),
            SitemapEntry(url="https://active.example.com/page-indexed"),
        ],
    )
    claimed = await search_container.crawl_url_repository.claim_pending_batch(
        active_domain.crawl_domain_id,
        limit=1,
    )
    assert len(claimed) == 1
    indexed_urls = await search_container.crawl_url_repository.claim_pending_batch(
        active_domain.crawl_domain_id,
        limit=1,
    )
    assert len(indexed_urls) == 1
    await search_container.crawl_url_repository.mark_indexed(
        indexed_urls[0].crawl_url_id,
        document_id=f"doc_{unique_id}",
        extract_content_hash=f"hash_{unique_id}",
        fetch_transport="http",
        extract_markdown="Example page markdown for crawl report test.",
        extract_title="Example page",
        extract_structural_signals=CrawlStructuralSignals(),
    )

    running_job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        trigger="manual",
        schedule_task_id=None,
    )
    completed_job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        trigger="scheduler",
        schedule_task_id=None,
    )
    await search_container.crawl_job_repository.finish(completed_job.crawl_job_id, status="completed")

    response = await search_client.get(f"/search/api/v1/crawl/profiles/{crawl_profile_id}/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["domains_total"] == 2
    assert payload["domains_due"] == 1
    assert _count_map(payload["domain_counts"]) == {"active": 1, "error": 1}
    assert _count_map(payload["url_counts"]) == {"fetching": 1, "indexed": 1}
    assert payload["running_job"]["crawl_job_id"] == running_job.crawl_job_id
    assert payload["latest_job"]["crawl_job_id"] == completed_job.crawl_job_id


@pytest.mark.asyncio
async def test_list_crawl_domains_filter(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="only-active.example.com", category="news")],
        next_crawl_after=now,
    )
    domains_page = await search_container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=10,
        offset=0,
    )
    error_domain = domains_page.items[0]
    await search_container.crawl_domain_repository.schedule_next(
        error_domain.crawl_domain_id,
        next_crawl_after=now,
        status="error",
        last_error="blocked",
    )

    response = await search_client.get(
        "/search/api/v1/crawl/domains",
        params={"crawl_profile_id": crawl_profile_id, "status": "error", "limit": 10, "offset": 0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["domain"] == "only-active.example.com"
    assert payload["items"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_list_crawl_urls_fetching(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="urls.example.com", category="news")],
        next_crawl_after=now,
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]
    await search_container.crawl_url_repository.upsert_from_sitemap(
        domain.crawl_domain_id,
        [SitemapEntry(url="https://urls.example.com/in-progress")],
    )
    claimed = await search_container.crawl_url_repository.claim_pending_batch(domain.crawl_domain_id, limit=1)
    assert len(claimed) == 1

    response = await search_client.get(
        "/search/api/v1/crawl/urls",
        params={
            "crawl_profile_id": crawl_profile_id,
            "crawl_status": "fetching",
            "limit": 10,
            "offset": 0,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["domain"] == "urls.example.com"
    assert payload["items"][0]["crawl_status"] == "fetching"


@pytest.mark.asyncio
async def test_list_crawl_jobs(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    first = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        trigger="manual",
        schedule_task_id=None,
    )
    await search_container.crawl_job_repository.finish(first.crawl_job_id, status="completed")
    second = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        trigger="scheduler",
        schedule_task_id=None,
    )

    response = await search_client.get(
        "/search/api/v1/crawl/jobs",
        params={"crawl_profile_id": crawl_profile_id, "limit": 10, "offset": 0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["crawl_job_id"] == second.crawl_job_id
    assert payload["items"][1]["crawl_job_id"] == first.crawl_job_id


@pytest.mark.asyncio
async def test_crawl_profile_summary_not_found(search_client, unique_id):
    response = await search_client.get(f"/search/api/v1/crawl/profiles/missing_{unique_id}/summary")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_crawl_domain_queues_discover(
    search_client,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context
    enqueued: list[tuple[str, tuple[object, ...]]] = []

    async def _capture(task_name: str, *args: object, **kwargs: object) -> None:
        enqueued.append((task_name, args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _capture,
    )

    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="run-now.example.com", category="news")],
        next_crawl_after=now + timedelta(days=1),
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]

    response = await search_client.post(
        f"/search/api/v1/crawl/domains/{domain.crawl_domain_id}/run",
        params={"crawl_profile_id": crawl_profile_id},
        json={},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["crawl_domain_id"] == domain.crawl_domain_id
    assert payload["crawl_profile_id"] == crawl_profile_id
    assert payload["action"] == "discover"
    assert payload["status"] == "queued"
    assert payload["crawl_job_id"]
    assert len(enqueued) == 1
    assert enqueued[0][0] == CRAWL_DISCOVER_DOMAIN_TASK_NAME
    assert enqueued[0][1][0] == domain.crawl_domain_id

    refreshed = await search_container.crawl_domain_repository.get(domain.crawl_domain_id)
    assert refreshed.status == "active"
    assert refreshed.next_crawl_after <= datetime.now(UTC)


async def _seed_crawl_urls(
    search_container,
    crawl_profile_id: str,
    unique_id: str,
) -> tuple[str, str]:
    """Returns (pending_crawl_url_id, indexed_crawl_url_id)."""
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=f"detail-{unique_id}.example.com", category="news")],
        next_crawl_after=now,
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]
    await search_container.crawl_url_repository.upsert_from_sitemap(
        domain.crawl_domain_id,
        [
            SitemapEntry(url=f"https://detail-{unique_id}.example.com/pending"),
            SitemapEntry(url=f"https://detail-{unique_id}.example.com/indexed"),
        ],
    )
    pending_batch = await search_container.crawl_url_repository.claim_pending_batch(
        domain.crawl_domain_id,
        limit=1,
    )
    assert len(pending_batch) == 1
    pending_id = pending_batch[0].crawl_url_id
    indexed_batch = await search_container.crawl_url_repository.claim_pending_batch(
        domain.crawl_domain_id,
        limit=1,
    )
    assert len(indexed_batch) == 1
    indexed_id = indexed_batch[0].crawl_url_id
    await search_container.crawl_url_repository.mark_indexed(
        indexed_id,
        document_id=f"doc_{unique_id}",
        extract_content_hash=f"hash_{unique_id}",
        fetch_transport="http",
        extract_markdown=f"Fetched markdown for {unique_id}",
        extract_title=f"Title {unique_id}",
        extract_structural_signals=CrawlStructuralSignals(),
    )
    return pending_id, indexed_id


@pytest.mark.asyncio
async def test_get_crawl_url_detail_pending(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    pending_id, _indexed_id = await _seed_crawl_urls(search_container, crawl_profile_id, unique_id)

    response = await search_client.get(
        f"/search/api/v1/crawl/urls/{pending_id}",
        params={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["url"]["crawl_url_id"] == pending_id
    assert payload["url"]["crawl_status"] == "fetching"
    assert payload["url"]["document_id"] is None
    assert payload["extract_markdown"] is None
    assert payload["indexed_content"] is None


@pytest.mark.asyncio
async def test_get_crawl_url_detail_indexed_extract(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    _pending_id, indexed_id = await _seed_crawl_urls(search_container, crawl_profile_id, unique_id)

    response = await search_client.get(
        f"/search/api/v1/crawl/urls/{indexed_id}",
        params={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["url"]["crawl_status"] == "indexed"
    assert payload["url"]["document_id"] == f"doc_{unique_id}"
    assert payload["url"]["fetch_transport"] == "http"
    assert payload["extract_title"] == f"Title {unique_id}"
    assert payload["extract_markdown"] == f"Fetched markdown for {unique_id}"
    assert payload["indexed_content"] is None


@pytest.mark.asyncio
async def test_get_crawl_url_detail_not_found(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)

    response = await search_client.get(
        f"/search/api/v1/crawl/urls/missing_{unique_id}",
        params={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_crawl_url_detail_with_rag_content(
    search_client,
    search_container,
    search_system_context,
    rag_client,
    auth_headers_system,
    unique_id,
    provider_litserve_service,
    rag_worker,
):
    _ = search_system_context, provider_litserve_service, rag_worker
    crawl_profile_id = await _create_profile(search_container, unique_id)
    profile = await search_container.crawl_profile_repository.get_with_index(crawl_profile_id)
    rag_namespace_id = profile.search_index.rag_namespace_id
    marker = f"crawl_detail_marker_{unique_id}"
    doc_text = (
        f"Indexed crawl page content with marker {marker}. "
        "Long enough text for chunking in RAG document content endpoint."
    )
    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/ingest-text",
        json={
            "text": doc_text,
            "document_name": "crawl-page.md",
            "metadata": {"page_summary": f"Summary for {unique_id}"},
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200
    document_id = ingest.json()["document_id"]

    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=f"rag-detail-{unique_id}.example.com", category="news")],
        next_crawl_after=now,
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]
    await search_container.crawl_url_repository.upsert_from_sitemap(
        domain.crawl_domain_id,
        [SitemapEntry(url=f"https://rag-detail-{unique_id}.example.com/page")],
    )
    claimed = await search_container.crawl_url_repository.claim_pending_batch(
        domain.crawl_domain_id,
        limit=1,
    )
    crawl_url_id = claimed[0].crawl_url_id
    await search_container.crawl_url_repository.mark_indexed(
        crawl_url_id,
        document_id=document_id,
        extract_content_hash=f"hash_{unique_id}",
        fetch_transport="browser",
        extract_markdown="Fetched body",
        extract_title="Fetched title",
        extract_structural_signals=CrawlStructuralSignals(),
    )

    response = await search_client.get(
        f"/search/api/v1/crawl/urls/{crawl_url_id}",
        params={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["indexed_content"] is not None
    assert payload["indexed_content"]["document_id"] == document_id
    assert marker in payload["indexed_content"]["markdown"]
    assert payload["indexed_content"]["page_summary"] == f"Summary for {unique_id}"
    assert payload["indexed_content"]["chunks_count"] >= 1


def _suppress_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(task_name: str, *args: object, **kwargs: object) -> None:
        _ = task_name, args, kwargs

    monkeypatch.setattr("apps.search.api.v1.crawl._kiq_task", _noop)


@pytest.mark.asyncio
async def test_patch_crawl_profile_updates_filters_and_limits(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)

    response = await search_client.patch(
        f"/search/api/v1/crawl/profiles/{crawl_profile_id}",
        json={
            "refresh_interval_seconds": 3600,
            "exclude_url_patterns": ["/private(/|$)"],
            "exclude_extensions": ["pdf", "mp4"],
            "llm_enrichment_enabled": True,
            "enrichment_model": "auto",
        },
    )
    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["refresh_interval_seconds"] == 3600
    assert profile["exclude_url_patterns"] == ["/private(/|$)"]
    assert profile["exclude_extensions"] == ["pdf", "mp4"]
    assert profile["llm_enrichment_enabled"] is True

    stored = await search_container.crawl_profile_repository.get_with_index(crawl_profile_id)
    assert stored.profile.refresh_interval_seconds == 3600
    assert stored.profile.exclude_extensions == ["pdf", "mp4"]
    assert stored.profile.llm_enrichment_enabled is True


@pytest.mark.asyncio
async def test_create_crawl_domain_with_seed_urls(
    search_client,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context
    _suppress_tick(monkeypatch)
    crawl_profile_id = await _create_profile(search_container, unique_id)

    response = await search_client.post(
        f"/search/api/v1/crawl/profiles/{crawl_profile_id}/domains",
        json={
            "domain": f"created-{unique_id}.example.com",
            "category": "manual",
            "refresh_interval_seconds": 7200,
            "seed_urls": [f"https://created-{unique_id}.example.com/page-a"],
        },
    )
    assert response.status_code == 201
    domain_payload = response.json()
    assert domain_payload["domain"] == f"created-{unique_id}.example.com"
    assert domain_payload["refresh_interval_seconds"] == 7200

    pending = await search_container.crawl_url_repository.count_pending(domain_payload["crawl_domain_id"])
    assert pending == 1


@pytest.mark.asyncio
async def test_create_crawl_domain_rejects_duplicate(
    search_client,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context
    _suppress_tick(monkeypatch)
    crawl_profile_id = await _create_profile(search_container, unique_id)
    body = {"domain": f"dup-{unique_id}.example.com"}

    first = await search_client.post(
        f"/search/api/v1/crawl/profiles/{crawl_profile_id}/domains",
        json=body,
    )
    assert first.status_code == 201
    second = await search_client.post(
        f"/search/api/v1/crawl/profiles/{crawl_profile_id}/domains",
        json=body,
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_patch_crawl_domain_pause_and_interval(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=f"patch-{unique_id}.example.com", category="news")],
        next_crawl_after=datetime.now(UTC),
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]

    response = await search_client.patch(
        f"/search/api/v1/crawl/domains/{domain.crawl_domain_id}",
        params={"crawl_profile_id": crawl_profile_id},
        json={"status": "paused", "refresh_interval_seconds": 43200},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "paused"
    assert payload["refresh_interval_seconds"] == 43200


@pytest.mark.asyncio
async def test_delete_crawl_domain(
    search_client,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=f"del-{unique_id}.example.com", category="news")],
        next_crawl_after=datetime.now(UTC),
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]

    response = await search_client.delete(
        f"/search/api/v1/crawl/domains/{domain.crawl_domain_id}",
        params={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 204

    remaining = await search_container.crawl_domain_repository.count_for_profile(crawl_profile_id)
    assert remaining == 0


@pytest.mark.asyncio
async def test_add_crawl_domain_urls(
    search_client,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context
    _suppress_tick(monkeypatch)
    crawl_profile_id = await _create_profile(search_container, unique_id)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=f"addurls-{unique_id}.example.com", category="news")],
        next_crawl_after=datetime.now(UTC),
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]

    response = await search_client.post(
        f"/search/api/v1/crawl/domains/{domain.crawl_domain_id}/urls",
        params={"crawl_profile_id": crawl_profile_id},
        json={
            "urls": [
                f"https://addurls-{unique_id}.example.com/a",
                f"https://addurls-{unique_id}.example.com/b",
            ],
        },
    )
    assert response.status_code == 202
    stats = response.json()
    assert stats["inserted"] == 2

    pending = await search_container.crawl_url_repository.count_pending(domain.crawl_domain_id)
    assert pending == 2


@pytest.mark.asyncio
async def test_recrawl_crawl_url_resets_to_pending(
    search_client,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context
    _suppress_tick(monkeypatch)
    crawl_profile_id = await _create_profile(search_container, unique_id)
    _pending_id, indexed_id = await _seed_crawl_urls(search_container, crawl_profile_id, unique_id)

    response = await search_client.post(
        f"/search/api/v1/crawl/urls/{indexed_id}/recrawl",
        params={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["crawl_status"] == "pending"

    refreshed = await search_container.crawl_url_repository.get(indexed_id)
    assert refreshed.crawl_status == "pending"
    assert refreshed.fetch_attempts == 0

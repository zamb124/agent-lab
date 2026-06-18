"""
Two-stage crawl pipeline integration tests.

Layer 1: fetch → raw ingest → indexed + search (must work without LLM).
Layer 2: async enrich from stored markdown → re-ingest (independent of HTTP refetch).

Enrichment LLM подменяется детерминированным CrawlEnrichedPage (граница LitServe),
HTTP fetch и RAG ingest — реальные.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.crawl.enrichment_skip import compute_enriched_content_hash
from tests.search.integration.crawl_two_stage_support import (
    REAL_CRAWL_DOMAIN,
    REAL_CRAWL_MARKER,
    REAL_CRAWL_QUERY,
    deterministic_enriched_page,
    install_enqueue_recorder,
    poll_index_search,
    run_layer1_fetch,
    run_layer2_enrich,
    setup_example_com_crawl,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(180, func_only=True),
]


@pytest.mark.asyncio
async def test_layer1_indexes_and_search_before_enrichment_with_llm_flag_enabled(
    search_client,
    rag_worker,
    provider_litserve_service,
    crawl_search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    """При llm_enrichment_enabled=true layer 1 индексирует raw и поиск работает до enrich."""
    _ = rag_worker, provider_litserve_service, search_system_context
    search_container = crawl_search_container
    enqueued = install_enqueue_recorder(monkeypatch)

    search_index_id, crawl_profile_id, crawl_domain_id, _rag_namespace_id = await setup_example_com_crawl(
        search_container,
        unique_id=unique_id,
        llm_enrichment_enabled=True,
    )

    job_id, crawl_url_id = await run_layer1_fetch(
        search_container,
        crawl_profile_id=crawl_profile_id,
        crawl_domain_id=crawl_domain_id,
    )

    crawl_url = await search_container.crawl_url_repository.get(crawl_url_id)
    assert crawl_url.crawl_status == "indexed"
    assert crawl_url.document_id is not None
    assert crawl_url.enriched_content_hash is None
    assert crawl_url.enrichment_model is None

    url, _canonical, markdown, title, content_hash = (
        await search_container.crawl_url_repository.get_layer1_snapshot(crawl_url_id)
    )
    assert REAL_CRAWL_DOMAIN in url
    assert len(markdown.strip()) >= 50
    assert title.strip()
    assert content_hash.strip()

    enrich_tasks = [item for item in enqueued if item[0] == "crawl_enrich_url"]
    assert len(enrich_tasks) == 1
    assert enrich_tasks[0][1:] == (crawl_url_id, job_id, crawl_profile_id)

    hit = await poll_index_search(
        search_client,
        search_index_id=search_index_id,
        query=REAL_CRAWL_QUERY,
        url_domain=REAL_CRAWL_DOMAIN,
        content_marker=REAL_CRAWL_MARKER,
        timeout_seconds=90.0,
    )
    assert hit["search_index_id"] == search_index_id
    assert hit["source_type"] == "platform_index"
    assert REAL_CRAWL_DOMAIN in hit["url"]


@pytest.mark.asyncio
async def test_layer2_enrich_uses_stored_markdown_without_http_refetch(
    search_client,
    rag_worker,
    provider_litserve_service,
    crawl_search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    """Layer 2 читает extract_markdown из БД; повторный HTTP fetch при enrich не вызывается."""
    _ = rag_worker, provider_litserve_service, search_system_context
    search_container = crawl_search_container
    install_enqueue_recorder(monkeypatch)

    search_index_id, crawl_profile_id, crawl_domain_id, _rag_namespace_id = await setup_example_com_crawl(
        search_container,
        unique_id=unique_id,
        llm_enrichment_enabled=True,
    )
    job_id, crawl_url_id = await run_layer1_fetch(
        search_container,
        crawl_profile_id=crawl_profile_id,
        crawl_domain_id=crawl_domain_id,
    )

    enriched_page = deterministic_enriched_page(unique_id)
    enrich_calls: list[str] = []

    async def _deterministic_enrich_markdown(*, markdown: str, url: str, profile, crawl_domain_id: str):
        enrich_calls.append(markdown)
        return enriched_page

    async def _forbidden_refetch(*args: object, **kwargs: object):
        raise AssertionError("HTTP refetch must not run during layer-2 enrich")

    monkeypatch.setattr(
        search_container.crawl_orchestrator_service._page_enrichment_service,
        "enrich_markdown",
        _deterministic_enrich_markdown,
    )
    monkeypatch.setattr(
        search_container.crawl_orchestrator_service._fetch_service,
        "fetch_markdown",
        _forbidden_refetch,
    )

    await run_layer2_enrich(
        search_container,
        crawl_url_id=crawl_url_id,
        crawl_job_id=job_id,
        crawl_profile_id=crawl_profile_id,
    )

    assert len(enrich_calls) == 1
    stored_markdown = enrich_calls[0]
    assert len(stored_markdown.strip()) >= 50

    crawl_url = await search_container.crawl_url_repository.get(crawl_url_id)
    assert crawl_url.crawl_status == "indexed"
    assert crawl_url.enriched_content_hash == compute_enriched_content_hash(enriched_page)
    assert crawl_url.enrichment_model == enriched_page.enrichment_model

    job_after = await search_container.crawl_job_repository.get(job_id)
    assert job_after.urls_enriched >= 1

    marker = f"TWO_STAGE_ENRICH_{unique_id}"
    hit = await poll_index_search(
        search_client,
        search_index_id=search_index_id,
        query=marker,
        url_domain=REAL_CRAWL_DOMAIN,
        content_marker=marker,
        timeout_seconds=90.0,
    )
    assert REAL_CRAWL_DOMAIN in hit["url"]


@pytest.mark.asyncio
async def test_layer2_enrichment_failure_preserves_layer1_index_and_search(
    search_client,
    rag_worker,
    provider_litserve_service,
    crawl_search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    """Ошибка LLM enrichment не сбрасывает indexed; поиск по raw layer-1 остаётся."""
    _ = rag_worker, provider_litserve_service, search_system_context
    search_container = crawl_search_container
    install_enqueue_recorder(monkeypatch)

    search_index_id, crawl_profile_id, crawl_domain_id, _rag_namespace_id = await setup_example_com_crawl(
        search_container,
        unique_id=unique_id,
        llm_enrichment_enabled=True,
    )
    job_id, crawl_url_id = await run_layer1_fetch(
        search_container,
        crawl_profile_id=crawl_profile_id,
        crawl_domain_id=crawl_domain_id,
    )

    async def _enrich_fail(*args: object, **kwargs: object):
        raise ValueError("simulated litserve enrichment failure")

    monkeypatch.setattr(
        search_container.crawl_orchestrator_service._page_enrichment_service,
        "enrich_markdown",
        _enrich_fail,
    )

    with pytest.raises(ValueError, match="simulated litserve enrichment failure"):
        await run_layer2_enrich(
            search_container,
            crawl_url_id=crawl_url_id,
            crawl_job_id=job_id,
            crawl_profile_id=crawl_profile_id,
        )

    crawl_url = await search_container.crawl_url_repository.get(crawl_url_id)
    assert crawl_url.crawl_status == "indexed"
    assert crawl_url.document_id is not None
    assert crawl_url.enriched_content_hash is None
    assert crawl_url.last_error is not None
    assert "simulated litserve enrichment failure" in crawl_url.last_error

    job_after = await search_container.crawl_job_repository.get(job_id)
    assert job_after.urls_enrichment_failed >= 1

    hit = await poll_index_search(
        search_client,
        search_index_id=search_index_id,
        query=REAL_CRAWL_QUERY,
        url_domain=REAL_CRAWL_DOMAIN,
        content_marker=REAL_CRAWL_MARKER,
        timeout_seconds=90.0,
    )
    assert REAL_CRAWL_DOMAIN in hit["url"]


@pytest.mark.asyncio
async def test_full_two_stage_pipeline_search_after_raw_then_after_enriched(
    search_client,
    rag_worker,
    provider_litserve_service,
    crawl_search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    """Полный прогон: search после layer 1 (raw), затем layer 2 и search по enriched marker."""
    _ = rag_worker, provider_litserve_service, search_system_context
    search_container = crawl_search_container
    install_enqueue_recorder(monkeypatch)

    search_index_id, crawl_profile_id, crawl_domain_id, _rag_namespace_id = await setup_example_com_crawl(
        search_container,
        unique_id=unique_id,
        llm_enrichment_enabled=True,
    )
    job_id, crawl_url_id = await run_layer1_fetch(
        search_container,
        crawl_profile_id=crawl_profile_id,
        crawl_domain_id=crawl_domain_id,
    )

    await poll_index_search(
        search_client,
        search_index_id=search_index_id,
        query=REAL_CRAWL_QUERY,
        url_domain=REAL_CRAWL_DOMAIN,
        content_marker=REAL_CRAWL_MARKER,
        timeout_seconds=90.0,
    )

    enriched_page = deterministic_enriched_page(unique_id)
    monkeypatch.setattr(
        search_container.crawl_orchestrator_service._page_enrichment_service,
        "enrich_markdown",
        AsyncMock(return_value=enriched_page),
    )

    await run_layer2_enrich(
        search_container,
        crawl_url_id=crawl_url_id,
        crawl_job_id=job_id,
        crawl_profile_id=crawl_profile_id,
    )

    marker = f"TWO_STAGE_ENRICH_{unique_id}"
    hit = await poll_index_search(
        search_client,
        search_index_id=search_index_id,
        query=marker,
        url_domain=REAL_CRAWL_DOMAIN,
        content_marker=marker,
        timeout_seconds=90.0,
    )
    assert REAL_CRAWL_DOMAIN in hit["url"]

    crawl_url = await search_container.crawl_url_repository.get(crawl_url_id)
    assert crawl_url.enriched_content_hash is not None
    assert crawl_url.crawl_status == "indexed"

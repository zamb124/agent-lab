"""Повторная индексация страницы crawl идёт в живой RAG."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.search.services.crawl.ingest_service import CrawlIngestService
from core.clients.rag_client import RagClient
from core.crawl.models import CrawlDomain, CrawlFetchResult
from core.search.index_models import SearchIndexDefinition
from tests.search.unit.crawl_enrichment_fixtures import sample_enriched_page

pytestmark = pytest.mark.asyncio


def _search_index(unique_id: str, namespace_id: str) -> SearchIndexDefinition:
    now = datetime.now(UTC)
    return SearchIndexDefinition(
        search_index_id=f"idx_{unique_id}",
        company_id="system",
        display_name="Reingest",
        rag_namespace_id=namespace_id,
        rag_collection_id=f"col_{unique_id}",
        enabled=True,
        search_enabled=True,
        created_at=now,
        updated_at=now,
    )


def _domain(unique_id: str) -> CrawlDomain:
    now = datetime.now(UTC)
    return CrawlDomain(
        crawl_domain_id=f"dom-{unique_id}",
        crawl_profile_id=f"cr_{unique_id}",
        domain="example.com",
        category="docs",
        status="active",
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )


def _fetched(unique_id: str) -> CrawlFetchResult:
    return CrawlFetchResult(
        url=f"https://example.com/{unique_id}",
        canonical_url=f"https://example.com/{unique_id}",
        markdown="# Raw\n\nOriginal markdown.",
        title="Original",
        content_hash=f"hash-{unique_id}",
        fetch_transport="http",
    )


async def _search_text(client: RagClient, namespace_id: str, query: str) -> str:
    payload = await client.search(namespace_id, query, limit=5)
    results = payload.get("results")
    if not isinstance(results, list):
        return ""
    parts: list[str] = []
    for item in results:
        if isinstance(item, dict):
            content = item.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "\n".join(parts)


@pytest.mark.timeout(60)
async def test_reingest_replaces_document_and_survives_missing_delete(
    rag_service: object,
    unique_id: str,
) -> None:
    _ = rag_service
    namespace_id = f"reingest_{unique_id}"
    document_id = f"doc_{unique_id}"
    client = RagClient()
    _ = await client.create_namespace(namespace_id, "crawl reingest")
    service = CrawlIngestService(client)
    search_index = _search_index(unique_id, namespace_id)
    first_marker = f"FIRST_{unique_id}"
    second_marker = f"SECOND_{unique_id}"

    missing_id = await service.reingest_enriched_page(
        search_index=search_index,
        crawl_job_id=f"job-{unique_id}",
        crawl_profile_id=f"cr_{unique_id}",
        domain=_domain(unique_id),
        document_id=document_id,
        fetched=_fetched(unique_id),
        enriched_page=sample_enriched_page(
            page_title=f"Title {unique_id}",
            page_summary="First pass",
            marker=first_marker,
        ),
    )
    assert missing_id == document_id
    first_hit = await _search_text(client, namespace_id, first_marker)
    assert first_marker in first_hit

    replaced_id = await service.reingest_enriched_page(
        search_index=search_index,
        crawl_job_id=f"job-{unique_id}",
        crawl_profile_id=f"cr_{unique_id}",
        domain=_domain(unique_id),
        document_id=document_id,
        fetched=_fetched(unique_id),
        enriched_page=sample_enriched_page(
            page_title=f"Title {unique_id}",
            page_summary="Second pass",
            marker=second_marker,
        ),
    )
    assert replaced_id == document_id
    second_hit = await _search_text(client, namespace_id, second_marker)
    assert second_marker in second_hit
    stale_hit = await _search_text(client, namespace_id, first_marker)
    assert first_marker not in stale_hit

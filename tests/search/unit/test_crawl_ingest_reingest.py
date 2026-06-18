"""CrawlIngestService re-ingest contract."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from apps.search.services.crawl.ingest_service import CrawlIngestService
from core.crawl.models import CrawlDomain, CrawlFetchResult
from core.rag.models import RAGIngestTextResponse
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig
from tests.search.unit.crawl_enrichment_fixtures import sample_enriched_page

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_reingest_deletes_then_ingests_with_same_document_id() -> None:
    now = datetime.now(UTC)
    search_index = SearchIndexDefinition(
        search_index_id="idx_test",
        company_id="system",
        display_name="Test",
        rag_namespace_id="idx_test:ns",
        rag_collection_id="idx_test",
        enabled=True,
        search_enabled=True,
        retrieval=SearchIndexRetrievalConfig(),
        created_at=now,
        updated_at=now,
    )
    domain = CrawlDomain(
        crawl_domain_id="dom-1",
        crawl_profile_id="cr_test",
        domain="example.com",
        category="docs",
        crawl_policy="allow",
        status="active",
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )
    fetched = CrawlFetchResult(
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        markdown="# Raw\n\nOriginal markdown.",
        title="Original",
        content_hash="hash-raw",
        fetch_transport="http",
    )
    enriched_page = sample_enriched_page(
        page_title="Enriched title",
        page_summary="Enriched summary",
    )
    rag_client = AsyncMock()
    rag_client.delete_namespace_document = AsyncMock(return_value={"status": "deleted"})
    rag_client.ingest_text = AsyncMock(
        return_value=RAGIngestTextResponse(
            document_id="idx_test:abc123",
            document_name="Enriched title",
            namespace_id="idx_test:ns",
            status="indexed",
            provider="pgvector",
        ),
    )

    service = CrawlIngestService(rag_client)
    document_id = "idx_test:abc123"
    result_id = await service.reingest_enriched_page(
        search_index=search_index,
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        domain=domain,
        document_id=document_id,
        fetched=fetched,
        enriched_page=enriched_page,
    )

    assert result_id == document_id
    rag_client.delete_namespace_document.assert_awaited_once_with("idx_test:ns", document_id)
    ingest_call = rag_client.ingest_text.await_args
    assert ingest_call is not None
    assert ingest_call.kwargs["document_id"] == document_id
    assert "Enriched title" in ingest_call.args[1]
    metadata = ingest_call.kwargs["metadata"]
    assert metadata is not None
    assert metadata["llm_enriched"] is True
    assert metadata["content_type"] == "documentation"
    assert metadata["primary_topic"] == "tech"

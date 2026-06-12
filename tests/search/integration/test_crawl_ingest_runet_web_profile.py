"""Crawl ingest passes runet_web index profile into RAG metadata."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from apps.search.services.crawl.ingest_service import CrawlIngestService
from core.config import get_settings
from core.crawl.models import CrawlDomain, CrawlFetchResult, CrawlIngestPayload
from core.rag.index_profile_registry import resolve_index_profile
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig


@pytest.mark.asyncio
async def test_ingest_page_attaches_runet_web_profile_config(unique_id) -> None:
    captured_metadata: dict[str, object] = {}

    class _RagClient:
        async def ingest_text(
            self,
            namespace_id: str,
            text: str,
            *,
            document_name: str,
            document_id: str,
            metadata: dict[str, object],
        ) -> object:
            _ = namespace_id, text, document_name
            captured_metadata.update(metadata)

            class _Response:
                def __init__(self, resolved_document_id: str) -> None:
                    self.document_id = resolved_document_id

            return _Response(document_id)

    now = datetime.now(UTC)
    search_index = SearchIndexDefinition(
        search_index_id=f"idx_{unique_id}"[:63],
        company_id="system",
        display_name="Runet web test",
        rag_namespace_id=f"idx_{unique_id}:ns",
        rag_collection_id=f"idx_{unique_id}",
        enabled=True,
        search_enabled=True,
        retrieval=SearchIndexRetrievalConfig(),
        indexing_profile_key="runet_web",
        created_at=now,
        updated_at=now,
    )
    domain = CrawlDomain(
        crawl_domain_id=str(__import__("uuid").uuid4()),
        crawl_profile_id="cr_test",
        domain="example.com",
        domain_rank=1,
        category="docs",
        crawl_policy="sitemap_only",
        status="active",
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )
    markdown = "# Runet profile test\n\nContent for runet_web profile ingest validation with enough length."
    canonical_url = "https://example.com/runet-profile-test"
    fetched = CrawlFetchResult(
        url=canonical_url,
        canonical_url=canonical_url,
        markdown=markdown,
        title="Runet profile test",
        heading_trail=["Runet profile test"],
        content_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        fetch_transport="http",
    )

    ingest_service = CrawlIngestService(_RagClient())  # pyright: ignore[reportArgumentType]
    document_id = await ingest_service.ingest_page(
        search_index=search_index,
        crawl_job_id="job-1",
        crawl_profile_id="cr_test",
        domain=domain,
        payload=CrawlIngestPayload(fetched=fetched),
    )
    assert document_id
    expected_profile = resolve_index_profile("runet_web")
    assert captured_metadata["index_profile_config"] == expected_profile.model_dump(mode="json")
    assert captured_metadata["source_url"] == canonical_url
    settings_profile = get_settings().rag.index_profiles["runet_web"]
    assert settings_profile.split.strategy == "semantic"
    assert settings_profile.lexical.enabled is True

"""Crawl ingest attaches trafilatura metadata to RAG document metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.search.services.crawl.ingest_service import CrawlIngestService
from apps.search.services.crawl.salient_terms_service import SalientTermsService
from core.crawl.models import CrawlDomain, CrawlFetchResult, CrawlIngestPayload
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig
from core.search.pointer_models import RunetPointerConfig, SalientTermsConfig


@pytest.mark.asyncio
async def test_ingest_page_attaches_html_title_and_meta_description() -> None:
    rag_client = MagicMock()
    rag_client.ingest_text = AsyncMock(return_value=MagicMock(document_id="runet:abc"))
    runet_config = RunetPointerConfig(
        index_mode="chunk_mirror",
        salient_terms=SalientTermsConfig(backend="local"),
    )
    service = CrawlIngestService(
        rag_client,
        runet_config,
        SalientTermsService(runet_config=runet_config),
    )
    fetched = CrawlFetchResult(
        url="https://habr.com/ru/articles/ingress/",
        canonical_url="https://habr.com/ru/articles/ingress",
        markdown="# H1\n\n" + "body " * 50,
        title="HTML title from fetch",
        html_title="HTML title from fetch",
        meta_description="Meta description text",
        publish_date="2024-06-01",
        content_hash="abc",
    )
    search_index = SearchIndexDefinition(
        search_index_id="runet",
        company_id="system",
        display_name="Runet",
        rag_namespace_id="runet:platform",
        rag_collection_id="runet",
        enabled=True,
        search_enabled=True,
        indexing_profile_key="runet_web",
        retrieval=SearchIndexRetrievalConfig(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    domain = CrawlDomain(
        crawl_domain_id="d1",
        crawl_profile_id="runet_platform",
        domain="habr.com",
        domain_rank=1,
        category="tech",
        crawl_policy="allow",
        status="active",
        next_crawl_after=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    _ = await service.ingest_page(
        search_index=search_index,
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=domain,
        payload=CrawlIngestPayload(fetched=fetched),
    )
    call_kwargs = rag_client.ingest_text.call_args.kwargs
    metadata = call_kwargs["metadata"]
    assert metadata["html_title"] == "HTML title from fetch"
    assert metadata["meta_description"] == "Meta description text"
    assert metadata["publish_date"] == "2024-06-01"
    assert metadata["canonical_url"] == "https://habr.com/ru/articles/ingress"

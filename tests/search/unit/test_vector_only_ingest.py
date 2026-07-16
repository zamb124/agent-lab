"""Tests for CrawlIngestService in vector_pointer mode (§4.10, §4.10.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.search.services.crawl.ingest_service import CrawlIngestService
from apps.search.services.crawl.salient_terms_service import SalientTermsService
from core.crawl.models import CrawlDomain, CrawlEnrichedChunk, CrawlEnrichedPage, CrawlFetchResult, CrawlIngestPayload
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig
from core.search.pointer_models import RunetPointerConfig, SalientTermsConfig


def _make_service(*, index_mode: str = "vector_pointer", **runet_kwargs: object) -> tuple[CrawlIngestService, MagicMock]:
    rag_client = MagicMock()
    rag_client.ingest_text = AsyncMock(return_value=MagicMock(document_id="runet:abc"))
    salient_cfg = runet_kwargs.pop("salient_terms", SalientTermsConfig(backend="local"))
    runet_config = RunetPointerConfig(
        index_mode=index_mode,  # type: ignore[arg-type]
        salient_terms=salient_cfg,
        **runet_kwargs,
    )
    salient_service = SalientTermsService(runet_config=runet_config)
    service = CrawlIngestService(rag_client, runet_config, salient_service)
    return service, rag_client


def _make_payload(markdown: str = "# Title\n\n" + "body " * 30) -> CrawlIngestPayload:
    fetched = CrawlFetchResult(
        url="https://habr.com/ru/articles/1/",
        canonical_url="https://habr.com/ru/articles/1",
        markdown=markdown,
        title="Title",
        html_title="HTML Title",
        meta_description="Meta description",
        content_hash="abc123",
    )
    return CrawlIngestPayload(fetched=fetched)


def _make_search_index() -> SearchIndexDefinition:
    return SearchIndexDefinition(
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


def _make_domain() -> CrawlDomain:
    return CrawlDomain(
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


@pytest.mark.asyncio
async def test_vector_pointer_calls_ingest_multiple_times_for_split_embed() -> None:
    service, rag_client = _make_service(
        index_mode="vector_pointer",
        index_study_strategy="split_embed",
        max_vectors_per_url=12,
    )
    md = "# Title\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B.\n"
    payload = _make_payload(md)
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    # split_embed with 2 sections + global = at least 2 calls
    assert rag_client.ingest_text.call_count >= 2


@pytest.mark.asyncio
async def test_vector_pointer_metadata_has_doc_type() -> None:
    service, rag_client = _make_service(index_mode="vector_pointer", index_study_strategy="lexical")
    payload = _make_payload()
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    call_kwargs = rag_client.ingest_text.call_args.kwargs
    assert call_kwargs["metadata"]["doc_type"] == "vector_pointer"
    assert call_kwargs["metadata"]["vector_role"] == "global"
    assert "index_study_strategy" in call_kwargs["metadata"]


@pytest.mark.asyncio
async def test_vector_pointer_metadata_includes_html_title() -> None:
    service, rag_client = _make_service(index_mode="vector_pointer")
    payload = _make_payload()
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    call_kwargs = rag_client.ingest_text.call_args.kwargs
    metadata = call_kwargs["metadata"]
    assert metadata.get("html_title") == "HTML Title"
    assert metadata.get("meta_description") == "Meta description"


@pytest.mark.asyncio
async def test_chunk_mirror_calls_ingest_once_with_full_markdown() -> None:
    service, rag_client = _make_service(index_mode="chunk_mirror")
    md = "# Title\n\n" + "body " * 50
    payload = _make_payload(md)
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    assert rag_client.ingest_text.call_count == 1
    call_args = rag_client.ingest_text.call_args
    # chunk_mirror sends the full markdown (or enriched)
    assert "body" in call_args.args[1]


@pytest.mark.asyncio
async def test_vector_pointer_persist_debug_false_sends_embed_text() -> None:
    """When persist_index_content_debug=False, embed_text is sent (semantically rich)."""
    service, rag_client = _make_service(
        index_mode="vector_pointer",
        persist_index_content_debug=False,
        index_study_strategy="lexical",
    )
    payload = _make_payload("# Kubernetes Ingress\n\n## TLS\n\nSetup cert-manager.\n")
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    # The text sent should be the compact embed_text (not full markdown, not ".")
    call_text = rag_client.ingest_text.call_args.args[1]
    # Must contain meaningful terms (Kubernetes, Ingress, TLS or cert-manager)
    assert any(t in call_text for t in ("Kubernetes", "Ingress", "TLS", "cert"))


@pytest.mark.asyncio
async def test_vector_pointer_llm_embed_uses_enriched_page() -> None:
    service, rag_client = _make_service(
        index_mode="vector_pointer",
        index_study_strategy="llm_embed",
    )
    enriched = CrawlEnrichedPage(
        page_summary="LLM page summary",
        chunks=[
            CrawlEnrichedChunk(
                content="full chunk body",
                metadata_summary="Section summary",
                hierarchy=["Раздел"],
            ),
        ],
        enrichment_model="qwen/test",
        enrichment_prompt_version="v1",
    )
    fetched = CrawlFetchResult(
        url="https://habr.com/ru/articles/1/",
        canonical_url="https://habr.com/ru/articles/1",
        markdown="# Title\n\n" + "body " * 30,
        title="Title",
        content_hash="abc123",
    )
    payload = CrawlIngestPayload(fetched=fetched, enriched_page=enriched)
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    assert rag_client.ingest_text.call_count >= 2
    metadata = rag_client.ingest_text.call_args.kwargs["metadata"]
    assert metadata["index_study_strategy"] == "llm_embed"
    assert metadata["llm_enriched"] is True
    assert metadata["page_summary"] == "LLM page summary"
    first_embed_text = rag_client.ingest_text.call_args_list[0].args[1]
    assert first_embed_text == "LLM page summary"


@pytest.mark.asyncio
async def test_vector_pointer_salient_terms_in_metadata() -> None:
    service, rag_client = _make_service(
        index_mode="vector_pointer",
        index_study_strategy="lexical",
        salient_terms_max=80,
    )
    payload = _make_payload("# CVE-2024-9999\n\nCritical vulnerability in OpenSSL v3.2.1.\n")
    _ = await service.ingest_page(
        search_index=_make_search_index(),
        crawl_job_id="job1",
        crawl_profile_id="runet_platform",
        domain=_make_domain(),
        payload=payload,
    )
    metadata = rag_client.ingest_text.call_args.kwargs["metadata"]
    salient = metadata.get("salient_terms", [])
    assert isinstance(salient, list)
    assert any("CVE" in t for t in salient)

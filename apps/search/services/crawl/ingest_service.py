"""Ingest crawled pages into RAG."""

from __future__ import annotations

import hashlib

from core.clients.rag_client import RagClient
from core.crawl.enrichment_skip import compute_enriched_content_hash
from core.crawl.models import CrawlDomain, CrawlIngestPayload
from core.rag.index_profile_registry import resolve_index_profile
from core.rag.models import RAGMetadata
from core.search.index_models import SearchIndexDefinition


class CrawlIngestService:
    def __init__(self, rag_client: RagClient) -> None:
        self._rag_client: RagClient = rag_client

    async def ingest_page(
        self,
        *,
        search_index: SearchIndexDefinition,
        crawl_job_id: str,
        crawl_profile_id: str,
        domain: CrawlDomain,
        payload: CrawlIngestPayload,
    ) -> str:
        fetched = payload.fetched
        canonical_hash = hashlib.sha256(fetched.canonical_url.encode("utf-8")).hexdigest()[:32]
        document_id = f"{search_index.search_index_id}:{canonical_hash}"
        index_profile = resolve_index_profile(search_index.indexing_profile_key)
        metadata: RAGMetadata = {
            "collection_id": search_index.rag_collection_id,
            "search_index_id": search_index.search_index_id,
            "company_id": search_index.company_id,
            "ttl_seconds": 0,
            "source_url": fetched.url,
            "canonical_url": fetched.canonical_url,
            "domain": domain.domain,
            "domain_rank": domain.domain_rank,
            "title": payload.ingest_title,
            "heading_trail": fetched.heading_trail,
            "crawl_profile_id": crawl_profile_id,
            "crawl_job_id": crawl_job_id,
            "lang": "ru",
            "index_profile_config": index_profile.model_dump(mode="json"),
            "extract_content_hash": fetched.content_hash,
        }
        if payload.enriched_page is not None:
            enriched_page = payload.enriched_page
            enriched_hash = compute_enriched_content_hash(enriched_page)
            metadata_summaries = [
                chunk.metadata_summary for chunk in enriched_page.chunks[:32]
            ]
            metadata["page_summary"] = enriched_page.page_summary
            metadata["metadata_summaries"] = metadata_summaries
            metadata["enrichment_model"] = enriched_page.enrichment_model
            metadata["enrichment_prompt_version"] = enriched_page.enrichment_prompt_version
            metadata["enriched_content_hash"] = enriched_hash
            metadata["llm_enriched"] = True
        response = await self._rag_client.ingest_text(
            search_index.rag_namespace_id,
            payload.ingest_markdown,
            document_name=payload.ingest_title,
            document_id=document_id,
            metadata=metadata,
        )
        return response.document_id

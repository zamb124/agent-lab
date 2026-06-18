"""Ingest crawled pages into RAG."""

from __future__ import annotations

import hashlib

from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.crawl.enrichment_skip import compute_enriched_content_hash
from core.crawl.models import (
    CrawlDomain,
    CrawlEnrichedPage,
    CrawlFetchResult,
    CrawlIngestPayload,
    CrawlPageFilterMetadata,
)
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
        document_id: str | None = None,
    ) -> str:
        fetched = payload.fetched
        if document_id is None:
            canonical_hash = hashlib.sha256(fetched.canonical_url.encode("utf-8")).hexdigest()[:32]
            document_id = f"{search_index.search_index_id}:{canonical_hash}"
        metadata = self._build_metadata(
            search_index=search_index,
            crawl_job_id=crawl_job_id,
            crawl_profile_id=crawl_profile_id,
            domain=domain,
            payload=payload,
            fetched=fetched,
        )
        response = await self._rag_client.ingest_text(
            search_index.rag_namespace_id,
            payload.ingest_markdown,
            document_name=payload.ingest_title,
            document_id=document_id,
            metadata=metadata,
        )
        return response.document_id

    async def reingest_enriched_page(
        self,
        *,
        search_index: SearchIndexDefinition,
        crawl_job_id: str,
        crawl_profile_id: str,
        domain: CrawlDomain,
        document_id: str,
        fetched: CrawlFetchResult,
        enriched_page: CrawlEnrichedPage,
    ) -> str:
        try:
            _ = await self._rag_client.delete_namespace_document(
                search_index.rag_namespace_id,
                document_id,
            )
        except ServiceClientError as exc:
            error_message = str(exc)
            if not error_message.startswith("HTTP 404"):
                raise
        payload = CrawlIngestPayload(fetched=fetched, enriched_page=enriched_page)
        return await self.ingest_page(
            search_index=search_index,
            crawl_job_id=crawl_job_id,
            crawl_profile_id=crawl_profile_id,
            domain=domain,
            payload=payload,
            document_id=document_id,
        )

    @staticmethod
    def _filter_metadata_to_rag_fields(filter_metadata: CrawlPageFilterMetadata) -> RAGMetadata:
        rag_fields: RAGMetadata = {
            "content_type": filter_metadata.content_type,
            "primary_topic": filter_metadata.primary_topic,
            "topic_tags": filter_metadata.topic_tags,
            "category_path": filter_metadata.category_path,
            "language": filter_metadata.language,
            "audience": filter_metadata.audience,
        }
        if filter_metadata.date_published is not None:
            rag_fields["date_published"] = filter_metadata.date_published.isoformat()
        if filter_metadata.date_modified is not None:
            rag_fields["date_modified"] = filter_metadata.date_modified.isoformat()
        if filter_metadata.date_precision is not None:
            rag_fields["date_precision"] = filter_metadata.date_precision
        if filter_metadata.freshness_relevance is not None:
            rag_fields["freshness_relevance"] = filter_metadata.freshness_relevance
        return rag_fields

    def _build_metadata(
        self,
        *,
        search_index: SearchIndexDefinition,
        crawl_job_id: str,
        crawl_profile_id: str,
        domain: CrawlDomain,
        payload: CrawlIngestPayload,
        fetched: CrawlFetchResult,
    ) -> RAGMetadata:
        index_profile = resolve_index_profile(search_index.indexing_profile_key)
        page_language = fetched.structural_signals.language
        document_language = page_language if page_language is not None else "ru"
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
            "lang": document_language,
            "index_profile_config": index_profile.model_dump(mode="json"),
            "extract_content_hash": fetched.content_hash,
        }
        if payload.enriched_page is not None:
            enriched_page = payload.enriched_page
            enriched_hash = compute_enriched_content_hash(enriched_page)
            filter_metadata = enriched_page.chunks[0].filter_metadata
            metadata["page_title"] = enriched_page.page_title
            metadata["page_summary"] = enriched_page.page_summary
            metadata["enrichment_model"] = enriched_page.enrichment_model
            metadata["enrichment_prompt_version"] = enriched_page.enrichment_prompt_version
            metadata["enriched_content_hash"] = enriched_hash
            metadata["llm_enriched"] = True
            metadata.update(self._filter_metadata_to_rag_fields(filter_metadata))
        return metadata

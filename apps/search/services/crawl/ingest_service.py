"""Ingest crawled pages into RAG.

Two modes controlled by RunetPointerConfig.index_mode:
  chunk_mirror   — legacy: full markdown → RAG (content stored as-is)
  vector_pointer — page-card: IndexStudyService builds compact embed texts;
                   one ingest_text call per IndexVectorSpec; no prose in content.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from apps.search.services.crawl.salient_terms_service import SalientTermsService
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
from core.search.index_study.service import IndexVectorSpec, apply_index_study
from core.search.pointer_models import (
    RunetPointerConfig,
    resolve_index_content_stub,
)


class CrawlIngestService:
    def __init__(
        self,
        rag_client: RagClient,
        runet_config: RunetPointerConfig,
        salient_terms_service: SalientTermsService,
    ) -> None:
        self._rag_client: RagClient = rag_client
        self._runet_config: RunetPointerConfig = runet_config
        self._salient_terms_service: SalientTermsService = salient_terms_service

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

        if self._runet_config.index_mode == "vector_pointer":
            return await self._ingest_vector_pointer(
                search_index=search_index,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                domain=domain,
                payload=payload,
                document_id=document_id,
            )

        return await self._ingest_chunk_mirror(
            search_index=search_index,
            crawl_job_id=crawl_job_id,
            crawl_profile_id=crawl_profile_id,
            domain=domain,
            payload=payload,
            document_id=document_id,
        )

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

    async def _ingest_vector_pointer(
        self,
        *,
        search_index: SearchIndexDefinition,
        crawl_job_id: str,
        crawl_profile_id: str,
        domain: CrawlDomain,
        payload: CrawlIngestPayload,
        document_id: str,
    ) -> str:
        """Vector-only ingest: study strategy → embed texts → one row per vector, no prose."""
        fetched = payload.fetched
        cfg = self._runet_config
        title = fetched.html_title or fetched.title
        indexed_at = datetime.now(UTC).isoformat()

        salient_terms = await self._salient_terms_service.extract(
            fetched.markdown,
            max_terms=cfg.salient_terms_max,
        )
        specs = apply_index_study(
            fetched.markdown,
            title,
            strategy=cfg.index_study_strategy,
            enriched_page=payload.enriched_page,
            salient_terms=salient_terms,
            max_vectors=cfg.max_vectors_per_url,
            salient_terms_max=cfg.salient_terms_max,
        )
        total_chunks = len(specs)

        last_document_id = document_id
        for spec in specs:
            metadata = self._build_pointer_metadata(
                search_index=search_index,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                domain=domain,
                payload=payload,
                spec=spec,
                total_chunks=total_chunks,
                indexed_at=indexed_at,
            )
            debug_preview = _build_debug_preview(spec) if cfg.persist_index_content_debug else None
            content = resolve_index_content_stub(
                persist_debug=cfg.persist_index_content_debug,
                debug_preview=debug_preview,
                stub=cfg.index_content_stub,
            )
            response = await self._rag_client.ingest_text(
                search_index.rag_namespace_id,
                content if cfg.persist_index_content_debug else spec.embed_text,
                document_name=title,
                document_id=document_id,
                metadata=metadata,
            )
            last_document_id = response.document_id

        return last_document_id

    def _build_pointer_metadata(
        self,
        *,
        search_index: SearchIndexDefinition,
        crawl_job_id: str,
        crawl_profile_id: str,
        domain: CrawlDomain,
        payload: CrawlIngestPayload,
        spec: IndexVectorSpec,
        total_chunks: int,
        indexed_at: str,
    ) -> RAGMetadata:
        fetched = payload.fetched
        metadata: RAGMetadata = {
            "collection_id": search_index.rag_collection_id,
            "search_index_id": search_index.search_index_id,
            "company_id": search_index.company_id,
            "ttl_seconds": 0,
            "source_url": fetched.url,
            "canonical_url": fetched.canonical_url,
            "domain": domain.domain,
            "domain_rank": domain.domain_rank,
            "title": fetched.html_title or fetched.title,
            "crawl_profile_id": crawl_profile_id,
            "crawl_job_id": crawl_job_id,
            "lang": "ru",
            "extract_content_hash": fetched.content_hash,
            "doc_type": "vector_pointer",
            "vector_role": spec.vector_role,
            "vector_index": spec.vector_index,
            "total_chunks": total_chunks,
            "index_study_strategy": self._runet_config.index_study_strategy,
            "salient_terms": spec.salient_terms,
            "section_titles": spec.section_titles,
            "indexed_at": indexed_at,
        }
        if fetched.html_title is not None:
            metadata["html_title"] = fetched.html_title
        if fetched.meta_description is not None:
            metadata["meta_description"] = fetched.meta_description
        if fetched.publish_date is not None:
            metadata["publish_date"] = fetched.publish_date
        if spec.section_title is not None:
            metadata["section_title"] = spec.section_title
        if spec.heading_trail:
            metadata["heading_trail"] = spec.heading_trail
        if payload.enriched_page is not None:
            enriched_page = payload.enriched_page
            enriched_hash = compute_enriched_content_hash(enriched_page)
            metadata["page_summary"] = enriched_page.page_summary
            metadata["enrichment_model"] = enriched_page.enrichment_model
            metadata["enrichment_prompt_version"] = enriched_page.enrichment_prompt_version
            metadata["enriched_content_hash"] = enriched_hash
            metadata["llm_enriched"] = True
        return metadata

    async def _ingest_chunk_mirror(
        self,
        *,
        search_index: SearchIndexDefinition,
        crawl_job_id: str,
        crawl_profile_id: str,
        domain: CrawlDomain,
        payload: CrawlIngestPayload,
        document_id: str,
    ) -> str:
        fetched = payload.fetched
        metadata = self._build_chunk_mirror_metadata(
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

    def _build_chunk_mirror_metadata(
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
        signals = fetched.structural_signals
        if signals.publisher is not None:
            metadata["publisher"] = signals.publisher
            metadata["site_name"] = signals.publisher
        if signals.og_image_url is not None:
            metadata["og_image_url"] = signals.og_image_url
        if fetched.html_title is not None:
            metadata["html_title"] = fetched.html_title
        if fetched.meta_description is not None:
            metadata["meta_description"] = fetched.meta_description
        if fetched.publish_date is not None:
            metadata["publish_date"] = fetched.publish_date
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


def _build_debug_preview(spec: IndexVectorSpec) -> str:
    """Build a human-readable debug preview of the embed_text for crawl report inspection."""
    role_tag = f"[{spec.vector_role}:{spec.vector_index}]"
    preview = spec.embed_text[:500]
    return f"{role_tag} {preview}".strip()

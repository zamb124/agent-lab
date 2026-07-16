"""Platform search index provider."""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import cast

from apps.search.config import SearchIndexProviderConfig
from apps.search.db.crawl_repositories import canonicalize_url
from apps.search.db.search_index_repository import SearchIndexRepository
from apps.search.errors import SearchIndexNotFoundError, SearchIndexSearchDisabledError
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import Context, clear_context, set_context
from core.rag.models import RAGMetadata, RAGSearchResult
from core.rag_indexing_schema import SearchChannelsDefaults
from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult
from core.search.index_models import SearchIndexDefinition
from core.search.models import SearchResultDocType
from core.search.pointer_models import RunetPointerConfig, is_vector_pointer_metadata
from core.search.presentation import (
    build_favicon_proxy_url,
    extract_domain_from_url,
    resolve_preview_image_url,
    resolve_site_name,
)
from core.types import require_json_array

_MIN_USEFUL_CHUNK_CHARS = 40
_MAX_RETRIEVE_LIMIT = 200


def _metadata_text_field(metadata: RAGMetadata, field: str) -> str | None:
    raw = metadata.get(field)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    return text


def _resolve_index_snippet(
    *,
    content: str,
    metadata: RAGMetadata,
    snippet_limit: int,
) -> str:
    page_summary = _metadata_text_field(metadata, "page_summary")
    chunk_text = content.strip()
    llm_enriched = metadata.get("llm_enriched") is True
    if page_summary is not None and llm_enriched:
        return page_summary[:snippet_limit]
    if page_summary is not None and len(chunk_text) < _MIN_USEFUL_CHUNK_CHARS:
        return page_summary[:snippet_limit]
    if page_summary is not None and chunk_text in page_summary:
        return page_summary[:snippet_limit]
    if page_summary is not None:
        combined = f"{page_summary}\n\n{chunk_text}"
        return combined[:snippet_limit]
    return content[:snippet_limit]


def _resolve_index_title(*, document_name: str, metadata: RAGMetadata) -> str:
    page_title = _metadata_text_field(metadata, "page_title")
    if page_title is not None:
        return page_title
    return document_name


def _rag_document_dedup_key(rag_result: RAGSearchResult) -> str:
    canonical_url = _metadata_text_field(rag_result.metadata, "canonical_url")
    if canonical_url is not None:
        return canonical_url
    if rag_result.document_id.strip():
        return f"doc:{rag_result.document_id.strip()}"
    source_url = _metadata_text_field(rag_result.metadata, "source_url")
    if source_url is not None:
        return source_url
    raise ValueError("RAG search result must have canonical_url, document_id, or source_url")


def _dedupe_rag_results(rag_results: list[RAGSearchResult]) -> list[RAGSearchResult]:
    best_by_key: dict[str, RAGSearchResult] = {}
    for rag_result in rag_results:
        dedup_key = _rag_document_dedup_key(rag_result)
        existing = best_by_key.get(dedup_key)
        if existing is None or rag_result.score > existing.score:
            best_by_key[dedup_key] = rag_result
    deduped = list(best_by_key.values())
    deduped.sort(key=lambda item: (-item.score, item.document_name))
    return deduped


class IndexSearchProvider:
    provider_id: str = "index"

    def __init__(
        self,
        config: SearchIndexProviderConfig,
        search_index_repository: SearchIndexRepository,
        rag_client: RagClient,
        build_system_context: Callable[[str], Awaitable[Context]],
        runet_config: RunetPointerConfig | None = None,
    ) -> None:
        self._config: SearchIndexProviderConfig = config
        self._search_index_repository: SearchIndexRepository = search_index_repository
        self._rag_client: RagClient = rag_client
        self._build_system_context: Callable[[str], Awaitable[Context]] = build_system_context
        self._runet_config: RunetPointerConfig | None = runet_config
        self._cache: dict[frozenset[str], tuple[float, list[SearchIndexDefinition]]] = {}

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]:
        index_ids = list(request.index_ids)
        started = time.perf_counter()
        if not self._config.enabled:
            return [], MetaSearchProviderStatus(
                ok=False,
                error="index provider is disabled",
                billing_resource_name="search:index",
            )
        if not index_ids:
            return [], MetaSearchProviderStatus(
                ok=False,
                error="index_ids are required for index provider",
                billing_resource_name="search:index",
            )
        if len(index_ids) > self._config.max_indexes_per_request:
            return [], MetaSearchProviderStatus(
                ok=False,
                error=f"too many index_ids: {len(index_ids)}",
                billing_resource_name="search:index",
            )

        try:
            definitions = await self._load_definitions(index_ids)
        except SearchIndexNotFoundError as exc:
            return [], MetaSearchProviderStatus(
                ok=False,
                error=str(exc),
                billing_resource_name="search:index",
            )
        except SearchIndexSearchDisabledError as exc:
            return [], MetaSearchProviderStatus(
                ok=False,
                error=str(exc),
                billing_resource_name="search:index",
            )

        retrieve_limit = self._resolve_retrieve_limit(request, definitions)
        trace_id = f"search:index:{uuid.uuid4().hex}"
        set_context(await self._build_system_context(trace_id))
        try:
            try:
                per_index_limit = max(1, math.ceil(retrieve_limit / len(definitions)))
                tasks = [
                    self._search_single_index(definition, request.query, per_index_limit)
                    for definition in definitions
                ]
                batches = await asyncio.gather(*tasks)
            except (ServiceClientError, ValueError) as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                return [], MetaSearchProviderStatus(
                    ok=False,
                    error=str(exc),
                    latency_ms=latency_ms,
                    results_count=0,
                    billing_resource_name="search:index",
                )
            merged: list[WebSearchResult] = []
            for batch in batches:
                merged.extend(batch)
            merged = _dedup_results_by_url(merged)
            merged.sort(key=lambda item: (-item.score, item.provider_rank, item.title))
            ranked: list[WebSearchResult] = []
            for rank, item in enumerate(merged[:retrieve_limit], start=1):
                ranked.append(item.model_copy(update={"rank": rank, "provider_rank": rank}))
            latency_ms = int((time.perf_counter() - started) * 1000)
            if not ranked:
                return [], MetaSearchProviderStatus(
                    ok=False,
                    error="index returned no results",
                    latency_ms=latency_ms,
                    results_count=0,
                    billing_resource_name="search:index",
                )
            return ranked, MetaSearchProviderStatus(
                ok=True,
                latency_ms=latency_ms,
                results_count=len(ranked),
                billing_resource_name="search:index",
            )
        finally:
            clear_context()

    def _resolve_retrieve_limit(
        self,
        request: MetaSearchRequest,
        definitions: list[SearchIndexDefinition],
    ) -> int:
        if request.retrieve_limit is not None:
            return min(request.retrieve_limit, _MAX_RETRIEVE_LIMIT)
        index_limits = [definition.retrieval.retrieve_limit for definition in definitions]
        default_limit = max(index_limits)
        needed = request.offset + request.limit
        return min(max(default_limit, needed), _MAX_RETRIEVE_LIMIT)

    async def _load_definitions(self, index_ids: list[str]) -> list[SearchIndexDefinition]:
        cache_key = frozenset(index_ids)
        ttl = self._config.registry_cache_ttl_seconds
        if ttl > 0 and cache_key in self._cache:
            cached_at, cached = self._cache[cache_key]
            if time.time() - cached_at <= ttl:
                return cached
        definitions = await self._search_index_repository.batch_get_search_enabled(
            index_ids,
            company_id="system",
        )
        if ttl > 0:
            self._cache[cache_key] = (time.time(), definitions)
        return definitions

    async def _search_single_index(
        self,
        definition: SearchIndexDefinition,
        query: str,
        retrieve_limit: int,
    ) -> list[WebSearchResult]:
        # Disable lexical FTS for vector_pointer indices: content stub is not
        # meaningful for FTS; semantic signal is carried by the dense embedding.
        use_lexical = definition.retrieval.lexical
        if (
            self._runet_config is not None
            and self._runet_config.index_mode == "vector_pointer"
        ):
            use_lexical = False
        channels = SearchChannelsDefaults(
            semantic=definition.retrieval.semantic,
            lexical=use_lexical,
        )
        per_channel_top_k = definition.retrieval.per_channel_top_k
        if per_channel_top_k is None:
            per_channel_top_k = max(retrieve_limit * 3, 150)
        raw = await self._rag_client.search(
            definition.rag_namespace_id,
            query,
            limit=retrieve_limit,
            filters={"collection_id": definition.rag_collection_id},
            channels=channels,
            rrf_k=definition.retrieval.rrf_k,
            per_channel_top_k=per_channel_top_k,
            rerank=definition.retrieval.rerank,
        )
        payload = raw
        results_raw = require_json_array(payload.get("results"), "rag search results")
        rag_results: list[RAGSearchResult] = []
        for item in results_raw:
            if isinstance(item, dict):
                rag_results.append(RAGSearchResult.model_validate(item))
        deduped_rag = _dedupe_rag_results(rag_results)
        out: list[WebSearchResult] = []
        for index, rag_result in enumerate(deduped_rag, start=1):
            mapped = self._map_result(
                rag_result,
                definition=definition,
                provider_rank=index,
            )
            if mapped is not None:
                out.append(mapped)
        return _collapse_multi_vector_by_document(out)

    def _map_result(
        self,
        rag_result: RAGSearchResult,
        *,
        definition: SearchIndexDefinition,
        provider_rank: int,
    ) -> WebSearchResult | None:
        metadata = rag_result.metadata
        source_url_value = metadata.get("source_url")
        if not isinstance(source_url_value, str) or not source_url_value.strip():
            return None
        source_url = source_url_value.strip()
        is_pointer = is_vector_pointer_metadata(metadata)
        snippet_limit = definition.retrieval.snippet_max_chars
        if is_pointer:
            snippet = _build_snippet(rag_result, snippet_limit=snippet_limit, is_pointer=True)
            heading_trail = _string_list(metadata.get("heading_trail"))
            salient_terms = _string_list(metadata.get("salient_terms"))
            title = rag_result.document_name or _optional_string(metadata.get("html_title")) or "Untitled"
        else:
            snippet = _resolve_index_snippet(
                content=rag_result.content,
                metadata=rag_result.metadata,
                snippet_limit=snippet_limit,
            )
            title = _resolve_index_title(
                document_name=rag_result.document_name,
                metadata=rag_result.metadata,
            )
            heading_trail = []
            heading_value = rag_result.metadata.get("heading_trail")
            if isinstance(heading_value, list):
                for entry in heading_value:
                    if isinstance(entry, str) and entry.strip():
                        heading_trail.append(entry.strip())
            salient_terms = []
        canonical_url = _optional_string(metadata.get("canonical_url")) or source_url
        try:
            canonical_url = canonicalize_url(canonical_url)
        except ValueError:
            canonical_url = source_url
        display_url = extract_domain_from_url(source_url)
        site_name = resolve_site_name(metadata=rag_result.metadata, display_url=display_url)
        preview_image_url = resolve_preview_image_url(rag_result.metadata)
        favicon_url = build_favicon_proxy_url(display_url)
        published_at = _metadata_text_field(rag_result.metadata, "date_published")
        doc_type: SearchResultDocType | None = "vector_pointer" if is_pointer else None
        return WebSearchResult(
            title=title,
            url=source_url,
            snippet=snippet,
            display_url=display_url,
            provider=self.provider_id,
            provider_rank=provider_rank,
            score=rag_result.score,
            published_at=published_at,
            source_type="platform_index",
            chunk_id=rag_result.chunk_id,
            document_id=rag_result.document_id,
            heading_trail=heading_trail,
            search_index_id=definition.search_index_id,
            site_name=site_name,
            favicon_url=favicon_url,
            preview_image_url=preview_image_url,
            doc_type=doc_type,
            canonical_url=canonical_url,
            section_title=_optional_string(metadata.get("section_title")),
            salient_terms=salient_terms,
            page_summary=_optional_string(metadata.get("page_summary")),
            html_title=_optional_string(metadata.get("html_title")),
            meta_description=_optional_string(metadata.get("meta_description")),
            extract_content_hash=_optional_string(metadata.get("extract_content_hash")),
            indexed_at=_optional_string(metadata.get("indexed_at")),
        )


def _build_snippet(
    rag_result: RAGSearchResult,
    *,
    snippet_limit: int,
    is_pointer: bool,
) -> str:
    if not is_pointer:
        return rag_result.content[:snippet_limit]

    metadata = rag_result.metadata
    parts: list[str] = []
    section_title = _optional_string(metadata.get("section_title"))
    if section_title:
        parts.append(section_title)
    meta_description = _optional_string(metadata.get("meta_description"))
    if meta_description:
        parts.append(meta_description)
    salient_terms = _string_list(metadata.get("salient_terms"))
    if salient_terms:
        parts.append(", ".join(salient_terms[:12]))
    page_summary = _optional_string(metadata.get("page_summary"))
    if page_summary:
        parts.append(page_summary)
    section_titles = _string_list(metadata.get("section_titles"))
    if section_titles:
        parts.append(" · ".join(section_titles[:6]))
    snippet = " — ".join(part for part in parts if part).strip()
    if not snippet:
        snippet = _optional_string(metadata.get("html_title")) or rag_result.document_name or ""
    return snippet[:snippet_limit]


def _collapse_multi_vector_by_document(results: list[WebSearchResult]) -> list[WebSearchResult]:
    best_by_document: dict[str, WebSearchResult] = {}
    for item in results:
        key = item.document_id or item.canonical_url or item.url
        existing = best_by_document.get(key)
        if existing is None or item.score > existing.score:
            best_by_document[key] = item
    return list(best_by_document.values())


def _dedup_results_by_url(results: list[WebSearchResult]) -> list[WebSearchResult]:
    best_by_url: dict[str, WebSearchResult] = {}
    for item in results:
        key = item.canonical_url or item.url
        existing = best_by_url.get(key)
        if existing is None or item.score > existing.score:
            best_by_url[key] = item
    return list(best_by_url.values())


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in cast(list[object], value):
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return out

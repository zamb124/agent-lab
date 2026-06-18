"""Platform RAG index search provider."""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from apps.search.config import SearchIndexProviderConfig
from apps.search.db.search_index_repository import SearchIndexRepository
from apps.search.errors import SearchIndexNotFoundError, SearchIndexSearchDisabledError
from core.clients.rag_client import RagClient
from core.context import Context, clear_context, set_context
from core.rag.models import RAGMetadata, RAGSearchResult
from core.rag_indexing_schema import SearchChannelsDefaults
from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult
from core.search.index_models import SearchIndexDefinition
from core.types import require_json_array

_MIN_USEFUL_CHUNK_CHARS = 40


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


class IndexSearchProvider:
    provider_id: str = "index"

    def __init__(
        self,
        config: SearchIndexProviderConfig,
        search_index_repository: SearchIndexRepository,
        rag_client: RagClient,
        build_system_context: Callable[[str], Awaitable[Context]],
    ) -> None:
        self._config: SearchIndexProviderConfig = config
        self._search_index_repository: SearchIndexRepository = search_index_repository
        self._rag_client: RagClient = rag_client
        self._build_system_context: Callable[[str], Awaitable[Context]] = build_system_context
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

        trace_id = f"search:index:{uuid.uuid4().hex}"
        set_context(await self._build_system_context(trace_id))
        try:
            per_index_limit = max(1, math.ceil(request.limit / len(definitions)))
            tasks = [
                self._search_single_index(definition, request.query, per_index_limit)
                for definition in definitions
            ]
            batches = await asyncio.gather(*tasks)
            merged: list[WebSearchResult] = []
            for batch in batches:
                merged.extend(batch)
            merged.sort(key=lambda item: (-item.score, item.provider_rank, item.title))
            ranked: list[WebSearchResult] = []
            for rank, item in enumerate(merged[: request.limit], start=1):
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
        limit: int,
    ) -> list[WebSearchResult]:
        channels = SearchChannelsDefaults(
            semantic=definition.retrieval.semantic,
            lexical=definition.retrieval.lexical,
        )
        raw = await self._rag_client.search(
            definition.rag_namespace_id,
            query,
            limit=limit,
            filters={"collection_id": definition.rag_collection_id},
            channels=channels,
            rrf_k=definition.retrieval.rrf_k,
            per_channel_top_k=definition.retrieval.per_channel_top_k,
            rerank=definition.retrieval.rerank,
        )
        payload = raw
        results_raw = require_json_array(payload.get("results"), "rag search results")
        out: list[WebSearchResult] = []
        for index, item in enumerate(results_raw, start=1):
            if not isinstance(item, dict):
                continue
            mapped = self._map_result(
                RAGSearchResult.model_validate(item),
                definition=definition,
                provider_rank=index,
            )
            if mapped is not None:
                out.append(mapped)
        return out

    def _map_result(
        self,
        rag_result: RAGSearchResult,
        *,
        definition: SearchIndexDefinition,
        provider_rank: int,
    ) -> WebSearchResult | None:
        source_url_value = rag_result.metadata.get("source_url")
        if not isinstance(source_url_value, str) or not source_url_value.strip():
            return None
        source_url = source_url_value.strip()
        snippet_limit = definition.retrieval.snippet_max_chars
        snippet = _resolve_index_snippet(
            content=rag_result.content,
            metadata=rag_result.metadata,
            snippet_limit=snippet_limit,
        )
        title = _resolve_index_title(
            document_name=rag_result.document_name,
            metadata=rag_result.metadata,
        )
        heading_trail: list[str] = []
        heading_value = rag_result.metadata.get("heading_trail")
        if isinstance(heading_value, list):
            for entry in heading_value:
                if isinstance(entry, str) and entry.strip():
                    heading_trail.append(entry.strip())
        display_url = urlparse(source_url).netloc
        return WebSearchResult(
            title=title,
            url=source_url,
            snippet=snippet,
            display_url=display_url,
            provider=self.provider_id,
            provider_rank=provider_rank,
            score=rag_result.score,
            source_type="platform_index",
            chunk_id=rag_result.chunk_id,
            document_id=rag_result.document_id,
            heading_trail=heading_trail,
            search_index_id=definition.search_index_id,
        )

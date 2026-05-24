"""
HTTP-контракт ``POST {RAG_API_V1_PREFIX}/namespaces/{id}/search`` (как ``SearchRequest`` в apps/rag).

Единая сборка path/body для ``RagClient`` и ``RAGRepository.search_namespace``.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from core.rag.models import RAGMetadataFilter, RAGSearchOptions
from core.types import JsonObject

RAG_API_V1_PREFIX = "/rag/api/v1"

SEARCH_REQUEST_OPTION_KEYS = frozenset(
    {"channels", "rrf_k", "per_channel_top_k", "rerank", "retrieval"}
)


def filter_search_request_options(raw: RAGSearchOptions | JsonObject | None) -> RAGSearchOptions | None:
    if raw is None:
        return None
    if isinstance(raw, RAGSearchOptions):
        return raw

    payload: JsonObject = {}
    for key in SEARCH_REQUEST_OPTION_KEYS:
        if key in raw:
            payload[key] = raw[key]
    if not payload:
        return None
    return RAGSearchOptions.model_validate(payload)


def merge_search_request_options(
    bind_opts: RAGSearchOptions | JsonObject | None,
    call_opts: RAGSearchOptions | JsonObject | None,
) -> RAGSearchOptions | None:
    bind_model = filter_search_request_options(bind_opts)
    call_model = filter_search_request_options(call_opts)
    if bind_model is None:
        return call_model
    if call_model is None:
        return bind_model
    return RAGSearchOptions(
        channels=call_model.channels if call_model.channels is not None else bind_model.channels,
        rrf_k=call_model.rrf_k if call_model.rrf_k is not None else bind_model.rrf_k,
        per_channel_top_k=(
            call_model.per_channel_top_k
            if call_model.per_channel_top_k is not None
            else bind_model.per_channel_top_k
        ),
        rerank=call_model.rerank if call_model.rerank is not None else bind_model.rerank,
        retrieval=call_model.retrieval if call_model.retrieval is not None else bind_model.retrieval,
    )


def build_namespace_search_path(
    namespace_id: str,
    *,
    provider: str | None = None,
) -> str:
    seg = quote(namespace_id, safe="")
    path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/search"
    if provider:
        path = f"{path}?{urlencode({'provider': provider})}"
    return path


def build_namespace_search_json_body(
    *,
    query: str,
    limit: int,
    filters: RAGMetadataFilter | None = None,
    merged_search_options: RAGSearchOptions | None = None,
) -> JsonObject:
    body: JsonObject = {"query": query, "limit": limit}
    if filters is not None:
        body["filters"] = filters
    if merged_search_options is not None:
        if merged_search_options.channels is not None:
            body["channels"] = {
                "semantic": merged_search_options.channels.semantic,
                "lexical": merged_search_options.channels.lexical,
            }
        if merged_search_options.rrf_k is not None:
            body["rrf_k"] = merged_search_options.rrf_k
        if merged_search_options.per_channel_top_k is not None:
            body["per_channel_top_k"] = merged_search_options.per_channel_top_k
        if merged_search_options.rerank is not None:
            body["rerank"] = merged_search_options.rerank
        if merged_search_options.retrieval is not None:
            body["retrieval"] = merged_search_options.retrieval
    return body

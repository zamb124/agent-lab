"""
HTTP-контракт ``POST {RAG_API_V1_PREFIX}/namespaces/{id}/search`` (как ``SearchRequest`` в apps/rag).

Единая сборка path/body для ``RagClient`` и ``RAGRepository.search_namespace``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

RAG_API_V1_PREFIX = "/rag/api/v1"

SEARCH_REQUEST_OPTION_KEYS = frozenset(
    {"channels", "rrf_k", "per_channel_top_k", "rerank", "retrieval"}
)


def filter_search_request_options(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    return {k: v for k, v in raw.items() if k in SEARCH_REQUEST_OPTION_KEYS}


def merge_search_request_options(
    bind_opts: dict[str, Any] | None,
    call_opts: dict[str, Any] | None,
) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    merged.update(filter_search_request_options(bind_opts))
    merged.update(filter_search_request_options(call_opts))
    return merged if merged else None


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
    filters: dict[str, Any] | None = None,
    merged_search_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query, "limit": limit}
    if filters is not None:
        body["filters"] = filters
    if merged_search_options:
        body.update(merged_search_options)
    return body

"""
Единое разрешение retrieval-опций RAG из platform ``search_defaults`` + call-level overrides.

Все HTTP/in-process/межсервисные вызовы поиска обязаны проходить через
``resolve_platform_search_options``, чтобы не было semantic-only там, где канон —
гибрид semantic+lexical с русской FTS и едиными rrf/rerank дефолтами.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.rag.models import RAGSearchOptions
from core.rag.rag_http_namespace_search import merge_search_request_options
from core.rag_indexing_schema import IndexProfileSearchDefaults, SearchChannelsDefaults

if TYPE_CHECKING:
    from core.config.base import BaseSettings

_PLATFORM_DEFAULT_CHANNELS = SearchChannelsDefaults(semantic=True, lexical=True)


def resolve_platform_search_options(
    *,
    settings: BaseSettings | None = None,
    profile_sd: IndexProfileSearchDefaults | None = None,
    overrides: RAGSearchOptions | None = None,
    per_channel_top_k: int | None = None,
) -> RAGSearchOptions:
    """
    Собирает ``RAGSearchOptions`` для вызова поиска.

    Приоритет полей: ``overrides`` (явный call-level) → ``profile_sd`` →
    ``settings.rag.document_indexing.search_defaults`` → platform defaults
    (hybrid channels).
    """
    if settings is None:
        from core.config.base import get_settings

        active_settings = get_settings()
    else:
        active_settings = settings

    effective_sd = profile_sd
    if effective_sd is None:
        effective_sd = active_settings.rag.document_indexing.search_defaults

    channels = _PLATFORM_DEFAULT_CHANNELS
    if effective_sd is not None and effective_sd.channels is not None:
        channels = effective_sd.channels

    rrf_k: int | None = None
    resolved_per_channel_top_k: int | None = per_channel_top_k
    rerank: bool | None = None
    rerank_max_candidates: int | None = None
    if effective_sd is not None:
        rrf_k = effective_sd.rrf_k
        if resolved_per_channel_top_k is None:
            resolved_per_channel_top_k = effective_sd.per_channel_top_k
        if effective_sd.reranker is not None:
            rerank = effective_sd.reranker.enabled
            rerank_max_candidates = effective_sd.reranker.max_candidates

    platform_base = RAGSearchOptions(
        channels=channels,
        rrf_k=rrf_k,
        per_channel_top_k=resolved_per_channel_top_k,
        rerank=rerank,
        rerank_max_candidates=rerank_max_candidates,
        retrieval=True,
    )
    return merge_search_request_options(platform_base, overrides) or platform_base


__all__ = ["resolve_platform_search_options"]

"""
Единое разрешение retrieval-опций RAG из platform ``search_defaults`` + call-level overrides.

Все HTTP/in-process/межсервисные вызовы поиска обязаны проходить через
``resolve_platform_search_options``, чтобы не было semantic-only там, где канон —
гибрид semantic+lexical с русской FTS и едиными rrf/rerank дефолтами.

Не импортирует ``core.config``: иначе цикл
``config.base → llm_context → memory → search_options_resolver → config.base``.
Settings передаётся явно (Protocol поверх ``.rag.document_indexing``).
"""

from __future__ import annotations

from typing import Protocol

from core.rag.models import RAGSearchOptions
from core.rag.rag_http_namespace_search import merge_search_request_options
from core.rag_indexing_schema import (
    IndexProfileConfig,
    IndexProfileSearchDefaults,
    SearchChannelsDefaults,
)

_PLATFORM_DEFAULT_CHANNELS = SearchChannelsDefaults(semantic=True, lexical=True)


class _RagWithDocumentIndexing(Protocol):
    @property
    def document_indexing(self) -> IndexProfileConfig: ...


class PlatformSearchSettings(Protocol):
    """Минимальный контракт settings для резолва platform search defaults."""

    @property
    def rag(self) -> _RagWithDocumentIndexing: ...


def resolve_platform_search_options(
    *,
    settings: PlatformSearchSettings,
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
    effective_sd = profile_sd
    if effective_sd is None:
        effective_sd = settings.rag.document_indexing.search_defaults

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


__all__ = ["PlatformSearchSettings", "resolve_platform_search_options"]

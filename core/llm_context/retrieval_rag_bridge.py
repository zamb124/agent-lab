"""Мост LLM context retrieval policy → RAGSearchOptions overrides."""

from __future__ import annotations

from core.llm_context.models import LLMContextRetrievalPolicy
from core.rag.models import RAGSearchOptions
from core.rag_indexing_schema import SearchChannelsDefaults


def _channels_from_retrieval_mode(mode: str) -> SearchChannelsDefaults:
    if mode == "hybrid":
        return SearchChannelsDefaults(semantic=True, lexical=True)
    if mode == "lexical":
        return SearchChannelsDefaults(semantic=False, lexical=True)
    return SearchChannelsDefaults(semantic=True, lexical=False)


def rag_search_options_override_from_retrieval(
    retrieval: LLMContextRetrievalPolicy,
) -> RAGSearchOptions:
    """Собирает call-level overrides для ``resolve_platform_search_options``."""
    if retrieval.mode == "off":
        return RAGSearchOptions(retrieval=False)

    return RAGSearchOptions(
        channels=_channels_from_retrieval_mode(retrieval.mode),
        rrf_k=retrieval.rrf_k,
        per_channel_top_k=retrieval.per_channel_top_k,
        rerank=retrieval.rerank,
        rerank_max_candidates=retrieval.rerank_max_candidates,
        retrieval=True,
        freshness_weight=retrieval.freshness_weight,
        freshness_half_life_days=retrieval.freshness_half_life_days,
    )


__all__ = ["rag_search_options_override_from_retrieval"]

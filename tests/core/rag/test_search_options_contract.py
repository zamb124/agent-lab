"""
Gate единообразия retrieval-опций RAG по всей платформе.

Каждое поле ``RAGSearchOptions`` обязано проходить сквозь все слои одинаково:
HTTP-контракт (``SEARCH_REQUEST_OPTION_KEYS`` + body builder + merge),
``RagClient.search``/``global_search`` и тул flows ``rag_search``.
Разъезд любого слоя с моделью — фейл этого теста.
"""

from __future__ import annotations

import inspect

from core.clients.rag_client import RagClient
from core.clients.rag_models import RagSearchArgs
from core.rag.models import RAGSearchOptions
from core.rag.rag_http_namespace_search import (
    SEARCH_REQUEST_OPTION_KEYS,
    build_namespace_search_json_body,
    merge_search_request_options,
)
from core.rag_indexing_schema import SearchChannelsDefaults

OPTION_FIELDS = frozenset(RAGSearchOptions.model_fields.keys())

_FULL_OPTIONS = RAGSearchOptions(
    channels=SearchChannelsDefaults(semantic=True, lexical=True),
    rrf_k=42,
    per_channel_top_k=77,
    rerank=True,
    rerank_max_candidates=13,
    retrieval=True,
    freshness_weight=0.4,
    freshness_half_life_days=21.5,
)


def test_http_option_keys_match_search_options_model() -> None:
    assert SEARCH_REQUEST_OPTION_KEYS == OPTION_FIELDS


def test_body_builder_serializes_every_option_field() -> None:
    body = build_namespace_search_json_body(
        query="q",
        limit=5,
        merged_search_options=_FULL_OPTIONS,
    )
    missing = OPTION_FIELDS - set(body.keys())
    assert not missing, f"build_namespace_search_json_body не сериализует опции: {sorted(missing)}"


def test_merge_prefers_call_options_for_every_field() -> None:
    bind = RAGSearchOptions(
        channels=SearchChannelsDefaults(semantic=True, lexical=False),
        rrf_k=1,
        per_channel_top_k=1,
        rerank=False,
        rerank_max_candidates=1,
        retrieval=False,
        freshness_weight=0.1,
        freshness_half_life_days=1.0,
    )
    merged = merge_search_request_options(bind, _FULL_OPTIONS)
    assert merged is not None
    assert merged.model_dump() == _FULL_OPTIONS.model_dump()


def test_rag_client_search_methods_accept_every_option_field() -> None:
    for method in (RagClient.search, RagClient.global_search):
        params = set(inspect.signature(method).parameters.keys())
        missing = OPTION_FIELDS - params
        assert not missing, f"RagClient.{method.__name__} не принимает опции: {sorted(missing)}"


def test_flows_rag_search_tool_accepts_every_option_field() -> None:
    params = set(RagSearchArgs.model_fields.keys())
    missing = OPTION_FIELDS - params
    assert not missing, f"flows tool rag_search не принимает опции: {sorted(missing)}"

"""Контракт локального реранкера (gateway / ``LocalRerankerEngine``) без поднятия HTTP."""

import pytest
from fastapi import HTTPException

from apps.provider_litserve.reranker.engines import LocalRerankerEngine, parse_rerank_body
from core.config.models import ProviderLitserveInfraConfig
from apps.provider_litserve.openai_server_contracts import placeholder_rerank_scores


def _cfg(**kwargs: object) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(**kwargs)


def test_placeholder_scores_length_matches_passages() -> None:
    scores = placeholder_rerank_scores("a b", ["a", "b c", "x"])
    assert {"scores": scores, "len": len(scores)} == {"scores": [1.0, 1.0, 0.0], "len": 3}


def test_engine_rerank_empty_passages() -> None:
    eng = LocalRerankerEngine(_cfg(backend="placeholder"))
    eng.setup(None)
    assert eng.rerank("q", []) == {"scores": []}


def test_engine_rerank_too_many_passages_422() -> None:
    eng = LocalRerankerEngine(_cfg(backend="placeholder", max_passages=2))
    eng.setup(None)
    with pytest.raises(HTTPException) as ei:
        eng.rerank("q", ["a", "b", "c"])
    assert {"status_code": ei.value.status_code, "reason": ei.value.detail["reason"]} == {
        "status_code": 422,
        "reason": "too_many_passages",
    }


def test_engine_rerank_matches_client_contract() -> None:
    eng = LocalRerankerEngine(_cfg(backend="placeholder"))
    eng.setup(None)
    out = eng.rerank("hello world", ["hello", "bye"])
    assert out == {"scores": [1.0, 0.0]}


def test_parse_rerank_body_valid() -> None:
    d = parse_rerank_body({"query": "q", "passages": ["a", "b"]})
    assert d == {"query": "q", "passages": ["a", "b"]}


def test_parse_rerank_body_extra_field_forbidden() -> None:
    with pytest.raises(HTTPException) as ei:
        parse_rerank_body({"query": "q", "passages": [], "extra": 1})
    assert {"status_code": ei.value.status_code} == {"status_code": 422}


def test_parse_rerank_body_not_object() -> None:
    with pytest.raises(HTTPException) as ei:
        parse_rerank_body([])
    assert {"status_code": ei.value.status_code} == {"status_code": 422}

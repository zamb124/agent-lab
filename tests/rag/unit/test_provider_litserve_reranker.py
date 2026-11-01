"""Контракт локального реранкера (gateway / ``LocalRerankerEngine``) без поднятия HTTP."""

import pytest

from apps.provider_litserve.catalog import ModelCatalog
from apps.provider_litserve.openai_server_contracts import placeholder_rerank_scores
from apps.provider_litserve.reranker.engines import LocalRerankerEngine, parse_rerank_body
from core.config.models import ProviderLitserveInfraConfig
from core.websocket import WsCommandError


def _cfg(**kwargs: object) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(**kwargs)


def _engine(**kwargs: object) -> LocalRerankerEngine:
    cfg = _cfg(**kwargs)
    return LocalRerankerEngine(cfg, ModelCatalog.from_seed(cfg))


def test_placeholder_scores_length_matches_passages() -> None:
    scores = placeholder_rerank_scores("a b", ["a", "b c", "x"])
    assert {"scores": scores, "len": len(scores)} == {"scores": [1.0, 1.0, 0.0], "len": 3}


def test_engine_rerank_empty_passages() -> None:
    eng = _engine(backend="placeholder")
    eng.setup(None)
    assert eng.rerank("q", []).model_dump() == {"scores": []}


def test_engine_rerank_too_many_passages_422() -> None:
    eng = _engine(backend="placeholder", max_passages=2)
    eng.setup(None)
    with pytest.raises(WsCommandError) as ei:
        eng.rerank("q", ["a", "b", "c"])
    assert {"code": ei.value.code, "reason": ei.value.error_params["reason"]} == {
        "code": "unprocessable",
        "reason": "too_many_passages",
    }


def test_engine_rerank_matches_client_contract() -> None:
    eng = _engine(backend="placeholder")
    eng.setup(None)
    out = eng.rerank("hello world", ["hello", "bye"])
    assert out.model_dump() == {"scores": [1.0, 0.0]}


def test_parse_rerank_body_valid() -> None:
    d = parse_rerank_body({"query": "q", "passages": ["a", "b"]})
    assert d.model_dump(exclude_none=True) == {"query": "q", "passages": ["a", "b"]}


def test_parse_rerank_body_extra_field_forbidden() -> None:
    with pytest.raises(WsCommandError) as ei:
        parse_rerank_body({"query": "q", "passages": [], "extra": 1})
    assert ei.value.code == "unprocessable"


def test_parse_rerank_body_not_object() -> None:
    with pytest.raises(WsCommandError) as ei:
        parse_rerank_body([])
    assert ei.value.code == "unprocessable"

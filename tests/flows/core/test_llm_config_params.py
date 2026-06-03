"""Параметры NodeLLMConfig для billing / stream."""

import pytest
from pydantic import ValidationError

from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.runtime.llm_config_params import (
    resolve_llm_config_stream_kwargs,
    split_llm_config_for_client,
    stream_kwargs_from_llm_config,
)
from core.state import ExecutionState


def test_split_llm_config_for_client_none():
    m, t, p, k, u, mt, fid, fb = split_llm_config_for_client(None)
    assert (m, t, p, k, u, mt, fid, fb) == (None, None, None, None, None, None, None, None)


def test_split_llm_config_for_client_full():
    ov = NodeLLMConfig(
        model="gpt-4o",
        temperature=0.5,
        provider="openrouter",
        api_key="k",
        base_url="https://x",
        max_tokens=512,
        folder_id="b1test",
        fallback_models=[{"provider": "openrouter", "model": "fallback"}],
    )
    parts = split_llm_config_for_client(ov)
    assert parts[:7] == (
        "gpt-4o",
        0.5,
        "openrouter",
        "k",
        "https://x",
        512,
        "b1test",
    )
    assert parts[7] is not None
    assert parts[7][0].provider == "openrouter"
    assert parts[7][0].model == "fallback"


def test_stream_kwargs_from_config_minimal():
    assert stream_kwargs_from_llm_config(None) == {}


def test_stream_kwargs_from_config_and_extra_merges_last_in_client():
    ov = NodeLLMConfig(
        top_p=0.9,
        seed=42,
        reasoning_effort="low",
        extra_request_body={"temperature": 0.01, "custom": True},
    )
    kw = stream_kwargs_from_llm_config(ov)
    assert kw["top_p"] == 0.9
    assert kw["seed"] == 42
    assert kw["reasoning_effort"] == "low"
    assert kw["extra_body"] == {"temperature": 0.01, "custom": True}


def test_node_llm_config_extra_must_be_object():
    with pytest.raises(ValidationError):
        NodeLLMConfig(extra_request_body=[])


def test_node_llm_config_splits_provider_prefixed_model():
    ov = NodeLLMConfig.model_validate({"model": "openrouter:openai/gpt-4o"})
    assert ov.provider == "openrouter"
    assert ov.model == "openai/gpt-4o"


def test_node_llm_config_no_split_vendor_slash():
    ov = NodeLLMConfig.model_validate({"model": "openai/gpt-4o"})
    assert ov.provider is None
    assert ov.model == "openai/gpt-4o"


def test_resolve_config_stream_kwargs_extra_headers_and_var():
    state = ExecutionState(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow-a:c1",
        variables={"tok": "Bearer zz"},
    )
    ov = NodeLLMConfig(
        extra_request_headers={"Authorization": "@var:tok", "X-Custom": "plain"},
    )
    kw = resolve_llm_config_stream_kwargs(ov, state)
    assert kw["extra_headers"]["Authorization"] == "Bearer zz"
    assert kw["extra_headers"]["X-Custom"] == "plain"


def test_node_llm_config_extra_headers_must_be_string_values():
    with pytest.raises(ValidationError):
        NodeLLMConfig(extra_request_headers={"X": 1})


def test_node_llm_config_skips_split_when_provider_set():
    ov = NodeLLMConfig.model_validate(
        {"provider": "openai", "model": "openrouter:should-not-split"}
    )
    assert ov.provider == "openai"
    assert ov.model == "openrouter:should-not-split"

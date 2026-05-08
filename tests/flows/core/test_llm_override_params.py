"""Параметры NodeLLMOverride для get_llm / stream."""

import pytest
from pydantic import ValidationError

from apps.flows.src.models.node_config import NodeLLMOverride
from apps.flows.src.runtime.llm_override_params import (
    resolve_override_stream_kwargs,
    split_llm_override_for_client,
    stream_kwargs_from_override,
)
from core.state import ExecutionState


def test_split_llm_override_for_client_none():
    m, t, p, k, u, mt, fid = split_llm_override_for_client(None)
    assert (m, t, p, k, u, mt, fid) == (None, None, None, None, None, None, None)


def test_split_llm_override_for_client_full():
    ov = NodeLLMOverride(
        model="gpt-4o",
        temperature=0.5,
        provider="openrouter",
        api_key="k",
        base_url="https://x",
        max_tokens=512,
        folder_id="b1test",
    )
    assert split_llm_override_for_client(ov) == (
        "gpt-4o",
        0.5,
        "openrouter",
        "k",
        "https://x",
        512,
        "b1test",
    )


def test_stream_kwargs_from_override_minimal():
    assert stream_kwargs_from_override(None) == {}


def test_stream_kwargs_from_override_and_extra_merges_last_in_client():
    ov = NodeLLMOverride(
        top_p=0.9,
        seed=42,
        reasoning_effort="low",
        extra_request_body={"temperature": 0.01, "custom": True},
    )
    kw = stream_kwargs_from_override(ov)
    assert kw["top_p"] == 0.9
    assert kw["seed"] == 42
    assert kw["reasoning_effort"] == "low"
    assert kw["extra_body"] == {"temperature": 0.01, "custom": True}


def test_node_llm_override_extra_must_be_object():
    with pytest.raises(ValidationError):
        NodeLLMOverride(extra_request_body=[])


def test_node_llm_override_splits_provider_prefixed_model():
    ov = NodeLLMOverride.model_validate({"model": "openrouter:openai/gpt-4o"})
    assert ov.provider == "openrouter"
    assert ov.model == "openai/gpt-4o"


def test_node_llm_override_no_split_vendor_slash():
    ov = NodeLLMOverride.model_validate({"model": "openai/gpt-4o"})
    assert ov.provider is None
    assert ov.model == "openai/gpt-4o"


def test_resolve_override_stream_kwargs_extra_headers_and_var():
    state = ExecutionState(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow-a:c1",
        variables={"tok": "Bearer zz"},
    )
    ov = NodeLLMOverride(
        extra_request_headers={"Authorization": "@var:tok", "X-Custom": "plain"},
    )
    kw = resolve_override_stream_kwargs(ov, state)
    assert kw["extra_headers"]["Authorization"] == "Bearer zz"
    assert kw["extra_headers"]["X-Custom"] == "plain"


def test_node_llm_override_extra_headers_must_be_string_values():
    with pytest.raises(ValidationError):
        NodeLLMOverride(extra_request_headers={"X": 1})


def test_node_llm_override_skips_split_when_provider_set():
    ov = NodeLLMOverride.model_validate(
        {"provider": "openai", "model": "openrouter:should-not-split"}
    )
    assert ov.provider == "openai"
    assert ov.model == "openrouter:should-not-split"

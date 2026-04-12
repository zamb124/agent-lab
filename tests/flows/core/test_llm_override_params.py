"""Параметры NodeLLMOverride для get_llm / stream."""

import pytest
from pydantic import ValidationError

from apps.flows.src.models.node_config import NodeLLMOverride
from apps.flows.src.runtime.llm_override_params import (
    split_llm_override_for_client,
    stream_kwargs_from_override,
)


def test_split_llm_override_for_client_none():
    m, t, p, k, u, mt = split_llm_override_for_client(None)
    assert (m, t, p, k, u, mt) == (None, None, None, None, None, None)


def test_split_llm_override_for_client_full():
    ov = NodeLLMOverride(
        model="gpt-4o",
        temperature=0.5,
        provider="openrouter",
        api_key="k",
        base_url="https://x",
        max_tokens=512,
    )
    assert split_llm_override_for_client(ov) == ("gpt-4o", 0.5, "openrouter", "k", "https://x", 512)


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

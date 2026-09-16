from __future__ import annotations

import pytest

from apps.flows.src.runtime.nodes import (
    _code_agent_metadata_from_inputs,
    _merge_code_agent_env,
    _merge_code_agent_metadata,
)


def test_merge_guest_env_from_uppercase_input_mapping() -> None:
    merged = _merge_code_agent_env(
        mapped={"TICKET": "from-guest"},
        inputs={"content": "hello", "MODEL_NAME": "auto"},
    )
    assert merged == {"TICKET": "from-guest", "MODEL_NAME": "auto"}


def test_merge_guest_env_from_env_bag() -> None:
    merged = _merge_code_agent_env(
        mapped={},
        inputs={"content": "hello", "env": {"FOO": "bar"}},
    )
    assert merged == {"FOO": "bar"}


def test_merge_guest_env_overlap_raises() -> None:
    with pytest.raises(ValueError, match="overlaps guest_env key TICKET"):
        _merge_code_agent_env(
            mapped={"TICKET": "a"},
            inputs={"TICKET": "b"},
        )


def test_merge_guest_env_reserved_input_raises() -> None:
    with pytest.raises(ValueError, match="reserved"):
        _merge_code_agent_env(
            mapped={},
            inputs={"OPENAI_API_KEY": "stolen"},
        )


def test_metadata_from_inputs_skips_env_keys() -> None:
    extra = _code_agent_metadata_from_inputs(
        {"content": "hello", "env": {"FOO": "bar"}, "TICKET": "t", "user": {"id": 1}}
    )
    assert extra == {"user": {"id": 1}}


def test_merge_metadata_overlap_raises() -> None:
    with pytest.raises(ValueError, match="overlaps"):
        _merge_code_agent_metadata({"user": 1}, {"user": 2})

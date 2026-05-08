"""Юнит-тесты JSON body_template (MappingResolver.resolve_json_template_tree)."""

import pytest

from apps.flows.src.mapping import MappingResolver
from core.state import ExecutionState


def test_resolve_json_template_state_and_var_and_literal():
    state = ExecutionState(
        task_id="t",
        context_id="c",
        user_id="u",
        session_id="s:s",
        message="hello",
        variables={"token": "tok-v"},
    )
    variables = state.variables or {}
    tree = {
        "m": "@state:message",
        "auth": "@var:token",
        "n": 1,
        "literal": "x",
    }
    out = MappingResolver.resolve_json_template_tree(tree, state, variables)
    assert out["m"] == "hello"
    assert out["auth"] == "tok-v"
    assert out["n"] == 1
    assert out["literal"] == "x"


def test_resolve_json_template_mixed_state_raises():
    state = ExecutionState(
        task_id="t",
        context_id="c",
        user_id="u",
        session_id="s:s",
    )
    with pytest.raises(ValueError, match="mixed text with @state"):
        MappingResolver.resolve_json_template_string(
            "a @state:message", state, {}
        )


def test_parse_and_resolve_body_template():
    state = ExecutionState(
        task_id="t",
        context_id="c",
        user_id="u",
        session_id="s:s",
        variables={"k": 99},
    )
    raw = '{"x": "@var:k"}'
    out = MappingResolver.parse_and_resolve_body_template(raw, state, state.variables)
    assert out == {"x": 99}

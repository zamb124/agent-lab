"""Юнит-тесты MappingResolver.resolve_interpolated_string (HITL / headers канон)."""

import pytest

from apps.flows.src.mapping import MappingResolver
from core.state import ExecutionState
from core.types import JsonObject
from core.variables import VariableResolutionError


def _state(
    *,
    content: str | None = None,
    response: str | None = None,
    variables: JsonObject | None = None,
) -> ExecutionState:
    return ExecutionState(
        task_id="t",
        context_id="c",
        user_id="u",
        session_id="s:s",
        content=content,
        response=response,
        variables=variables if variables is not None else {},
    )


def test_interpolated_mixed_state_content() -> None:
    state = _state(content="Нужна помощь")
    out = MappingResolver.resolve_interpolated_string(
        "Оператор: @state:content",
        state,
    )
    assert out == "Оператор: Нужна помощь"


def test_interpolated_whole_state_ref() -> None:
    state = _state(content="from-state")
    out = MappingResolver.resolve_interpolated_string("@state:content", state)
    assert out == "from-state"


def test_interpolated_var_token() -> None:
    state = _state(variables={"queue_label": "VIP"})
    out = MappingResolver.resolve_interpolated_string(
        "Очередь @var:queue_label",
        state,
    )
    assert out == "Очередь VIP"


def test_interpolated_whole_var_ref() -> None:
    state = _state(variables={"title": "T1"})
    out = MappingResolver.resolve_interpolated_string("@var:title", state)
    assert out == "T1"


def test_interpolated_mixed_state_and_var() -> None:
    state = _state(content="hi", variables={"label": "VIP"})
    out = MappingResolver.resolve_interpolated_string(
        "[@var:label] @state:content",
        state,
    )
    assert out == "[VIP] hi"


def test_interpolated_missing_state_raises() -> None:
    state = _state()
    with pytest.raises(ValueError, match="@state:content resolved to None"):
        _ = MappingResolver.resolve_interpolated_string(
            "x @state:content", state
        )


def test_interpolated_missing_var_token_raises() -> None:
    state = _state()
    with pytest.raises(VariableResolutionError):
        _ = MappingResolver.resolve_interpolated_string("x @var:absent", state)


def test_interpolated_variables_overlay_whole_var() -> None:
    state = _state(variables={"title": "from-state-vars"})
    out = MappingResolver.resolve_interpolated_string(
        "@var:title",
        state,
        variables={"title": "from-local"},
    )
    assert out == "from-local"


def test_interpolated_variables_overlay_mixed_var() -> None:
    state = _state(variables={"title": "from-state-vars"})
    out = MappingResolver.resolve_interpolated_string(
        "T: @var:title",
        state,
        variables={"title": "from-local"},
    )
    assert out == "T: from-local"


def test_http_header_allows_mixed_state() -> None:
    state = _state(content="cid-1")
    out = MappingResolver.resolve_http_header_value(
        "trace=@state:content",
        state,
        state.variables,
    )
    assert out == "trace=cid-1"


def test_json_template_still_forbids_mixed_state() -> None:
    state = _state(content="x")
    with pytest.raises(ValueError, match="mixed text with @state"):
        _ = MappingResolver.resolve_json_template_string(
            "a @state:content", state, {}
        )

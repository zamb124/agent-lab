"""Запись в ExecutionState по dotted-пути: общий путь ui-action, тула ``state_set`` и кода."""

from __future__ import annotations

import pytest

from core.state import ExecutionState
from core.state.mutation_policy import FrozenStateFieldError
from core.state.state_path import assign_state_path


def _state(unique_id: str) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id="u1",
        session_id=f"state-path:{unique_id}",
    )


def test_top_level_assign_creates_and_overwrites_extra_fields(unique_id: str) -> None:
    state = _state(unique_id)
    assign_state_path(state, "name", "Ann")
    assign_state_path(state, "count", 1)
    assert state["name"] == "Ann" and state["count"] == 1
    assign_state_path(state, "name", None)
    assert state["name"] is None
    assign_state_path(state, "response", "answer")
    assert state.response == "answer"


def test_nested_assign_builds_objects_and_keeps_siblings(unique_id: str) -> None:
    state = _state(unique_id)
    assign_state_path(state, "order.customer.email", "a@b.c")
    assign_state_path(state, "order.customer.name", "Ann")
    assign_state_path(state, "order.total", 10)
    assert state["order"] == {"customer": {"email": "a@b.c", "name": "Ann"}, "total": 10}
    assign_state_path(state, "order.customer", {"replaced": True})
    assert state["order"] == {"customer": {"replaced": True}, "total": 10}


def test_nested_assign_does_not_mutate_the_previous_container(unique_id: str) -> None:
    state = _state(unique_id)
    assign_state_path(state, "order", {"customer": {"email": "old"}})
    previous = state["order"]
    assign_state_path(state, "order.customer.email", "new")
    assert previous == {"customer": {"email": "old"}}
    assert state["order"] == {"customer": {"email": "new"}}


def test_scalar_or_list_in_the_middle_of_the_path_is_an_error(unique_id: str) -> None:
    state = _state(unique_id)
    assign_state_path(state, "order", "not an object")
    with pytest.raises(ValueError, match="state path 'order.total' parent must be a JSON object"):
        assign_state_path(state, "order.total", 1)
    assign_state_path(state, "items", [1, 2])
    with pytest.raises(ValueError, match="state path 'items.0' parent must be a JSON object"):
        assign_state_path(state, "items.0", 1)
    assert state["order"] == "not an object" and state["items"] == [1, 2]


@pytest.mark.parametrize("path", ["", ".", "a.", ".a", "a..b"])
def test_empty_segments_are_rejected(unique_id: str, path: str) -> None:
    with pytest.raises(ValueError, match="invalid state path"):
        assign_state_path(_state(unique_id), path, 1)


@pytest.mark.parametrize("path", ["task_id", "interrupt.payload", "node_history", "ui_slots.top"])
def test_frozen_roots_cannot_be_assigned(unique_id: str, path: str) -> None:
    state = _state(unique_id)
    with pytest.raises(FrozenStateFieldError):
        assign_state_path(state, path, "x")
    assert state.task_id == f"task-{unique_id}"


def test_declared_object_fields_accept_nested_paths(unique_id: str) -> None:
    state = _state(unique_id)
    assign_state_path(state, "variables.theme", "dark")
    assert state.variables == {"theme": "dark"}
    assign_state_path(state, "variables.nested.flag", True)
    assert state.variables == {"theme": "dark", "nested": {"flag": True}}

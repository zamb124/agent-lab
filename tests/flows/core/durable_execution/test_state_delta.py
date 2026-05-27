from apps.flows.src.durable_execution import apply_state_delta, build_state_delta
from core.state import ExecutionState


def _state(**overrides: object) -> ExecutionState:
    data: dict[str, object] = {
        "task_id": "task-1",
        "context_id": "ctx-1",
        "user_id": "user-1",
        "session_id": "flow-1:ctx-1",
        "content": "hello",
        "branch_id": "default",
        "variables": {"a": 1},
        "tool_results": {"t1": {"ok": True}},
    }
    data.update(overrides)
    return ExecutionState.model_validate(data)


def test_state_delta_roundtrip_from_empty() -> None:
    state = _state(response="ok", current_nodes=["n1"])

    delta = build_state_delta(None, state)
    restored = apply_state_delta(None, delta)

    assert restored.model_dump(mode="json", exclude_none=False) == state.model_dump(
        mode="json",
        exclude_none=False,
    )


def test_state_delta_roundtrip_incremental_map_and_fields() -> None:
    before = _state(variables={"a": 1, "remove_me": True}, current_nodes=["n1"])
    after = _state(
        variables={"a": 2, "b": 3},
        tool_results={},
        current_nodes=["n2"],
        response="done",
    )

    delta = build_state_delta(before, after)
    restored = apply_state_delta(before, delta)

    assert delta.variables_set == {"a": 2, "b": 3}
    assert delta.variables_delete == ["remove_me"]
    assert delta.tool_results_delete == ["t1"]
    assert restored.model_dump(mode="json", exclude_none=False) == after.model_dump(
        mode="json",
        exclude_none=False,
    )


def test_state_delta_preserves_json_string_whitespace() -> None:
    before = _state(raw_input="apple, banana, cherry")
    after = _state(
        raw_input="apple, banana, cherry",
        extracted_data={"items": ["apple", " banana", " cherry"], "count": 3},
    )

    delta = build_state_delta(before, after)
    restored = apply_state_delta(before, delta)

    assert delta.fields_set["extracted_data"] == {
        "items": ["apple", " banana", " cherry"],
        "count": 3,
    }
    assert restored.model_dump(mode="json", exclude_none=False) == after.model_dump(
        mode="json",
        exclude_none=False,
    )


def test_state_delta_preserves_extra_field_set_to_null() -> None:
    before = _state(to_remove="value", keep="value")
    after = _state(to_remove=None, keep="value")

    delta = build_state_delta(before, after)
    restored = apply_state_delta(before, delta)

    assert delta.fields_set["to_remove"] is None
    assert "to_remove" not in delta.fields_unset
    assert restored.model_dump(mode="json", exclude_none=False) == after.model_dump(
        mode="json",
        exclude_none=False,
    )

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


def _dump(state: ExecutionState) -> dict[str, object]:
    return state.model_dump(mode="json", exclude_none=False)


def _message(message_id: str, role: str, text: str) -> dict[str, object]:
    return {"messageId": message_id, "role": role, "parts": [{"text": text}]}


def test_state_delta_appends_messages_when_history_grows() -> None:
    before = _state(messages=[_message("m1", "ROLE_USER", "hi")])
    after = _state(
        messages=[_message("m1", "ROLE_USER", "hi"), _message("m2", "ROLE_AGENT", "hello")],
    )

    delta = build_state_delta(before, after)

    assert len(delta.messages_append) == 1
    assert "messages" not in delta.fields_set
    assert _dump(apply_state_delta(before, delta)) == _dump(after)


def test_state_delta_rewrites_messages_when_history_is_not_a_prefix() -> None:
    before = _state(messages=[_message("m1", "ROLE_USER", "hi"), _message("m2", "ROLE_AGENT", "a")])
    after = _state(messages=[_message("m3", "ROLE_USER", "compacted")])

    delta = build_state_delta(before, after)

    assert delta.messages_append == []
    assert isinstance(delta.fields_set["messages"], list)
    assert _dump(apply_state_delta(before, delta)) == _dump(after)


def test_state_delta_unsets_declared_field_and_drops_removed_extra_field() -> None:
    before = _state(response="done", extra_field="x")
    after_data = _dump(_state(response="done", extra_field="x"))
    after_data["response"] = None
    del after_data["extra_field"]
    after = ExecutionState.model_validate(after_data)

    delta = build_state_delta(before, after)

    assert "response" in delta.fields_unset
    assert "extra_field" in delta.fields_unset
    assert "response" not in delta.fields_set
    restored = apply_state_delta(before, delta)
    assert restored.response is None
    assert "extra_field" not in _dump(restored)
    assert _dump(restored) == _dump(after)


def test_state_delta_carries_flow_ui_slots_and_action() -> None:
    before = _state()
    after = _state(
        ui_action={"name": "submit", "source": "send", "payload": {"draft_id": "d1"}},
        ui_slots={
            "summary": [
                {"type": "metric", "block_id": "total", "label": "Total", "value": "{total}"},
                {
                    "type": "section",
                    "block_id": "s",
                    "blocks": [{"type": "divider", "block_id": "d"}],
                },
            ]
        },
        nested_states={"child": {"content": "x"}},
    )

    delta = build_state_delta(before, after)
    restored = apply_state_delta(before, delta)

    assert set(delta.fields_set) >= {"ui_action", "ui_slots"}
    assert list(delta.nested_states_set) == ["child"]
    assert [block.block_id for block in restored.ui_slots["summary"]] == ["total", "s"]
    assert restored.ui_action is not None and restored.ui_action.name == "submit"
    assert _dump(restored) == _dump(after)

    cleared = build_state_delta(after, _state(nested_states={}))
    assert "ui_action" in cleared.fields_unset
    assert cleared.fields_set["ui_slots"] == {}
    assert cleared.nested_states_delete == ["child"]
    assert _dump(apply_state_delta(after, cleared)) == _dump(_state(nested_states={}))


def test_state_delta_from_empty_carries_messages_and_maps() -> None:
    state = _state(
        messages=[_message("m1", "ROLE_USER", "hi")],
        nested_states={"n": {"content": "x"}},
    )

    delta = build_state_delta(None, state)

    assert len(delta.messages_append) == 1
    assert list(delta.nested_states_set) == ["n"]
    assert "messages" not in delta.fields_set
    assert _dump(apply_state_delta(None, delta)) == _dump(state)

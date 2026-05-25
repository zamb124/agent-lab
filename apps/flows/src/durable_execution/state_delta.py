"""Build and apply domain-aware ExecutionState deltas."""

from __future__ import annotations

from copy import deepcopy

from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_object

from .models import ExecutionStateDelta

_MAP_FIELDS = {
    "variables",
    "tool_results",
    "nested_states",
    "child_workflows",
}
_SPECIAL_FIELDS = {"messages", *_MAP_FIELDS}


def _state_json(state: ExecutionState) -> JsonObject:
    raw = state.model_dump(mode="json", exclude_none=False)
    raw.pop("flow_config", None)
    return require_json_object(raw, "ExecutionState")


def _json_map(value: object, field_name: str) -> JsonObject:
    if value is None:
        return {}
    return require_json_object(value, field_name)


def _build_map_delta(
    before: JsonObject,
    after: JsonObject,
) -> tuple[JsonObject, list[str]]:
    set_values: JsonObject = {}
    delete_keys: list[str] = []

    for key, after_value in after.items():
        if key not in before or before[key] != after_value:
            set_values[key] = after_value
    for key in before:
        if key not in after:
            delete_keys.append(key)
    return set_values, sorted(delete_keys)


def build_state_delta(
    before: ExecutionState | None,
    after: ExecutionState,
) -> ExecutionStateDelta:
    """Return a compact semantic delta from before to after."""
    after_json = _state_json(after)
    if before is None:
        fields_set = {
            key: value
            for key, value in after_json.items()
            if key not in _SPECIAL_FIELDS
        }
        variables_set = _json_map(after_json.get("variables"), "variables")
        tool_results_set = _json_map(after_json.get("tool_results"), "tool_results")
        nested_states_set = _json_map(after_json.get("nested_states"), "nested_states")
        child_workflows_set = _json_map(after_json.get("child_workflows"), "child_workflows")
        messages_raw = after_json.get("messages") or []
        if not isinstance(messages_raw, list):
            raise ValueError("ExecutionState.messages must be a list")
        return ExecutionStateDelta(
            messages_append=messages_raw,
            variables_set=variables_set,
            tool_results_set=tool_results_set,
            nested_states_set=nested_states_set,
            child_workflows_set=child_workflows_set,
            fields_set=fields_set,
        )

    before_json = _state_json(before)
    before_messages = before_json.get("messages") or []
    after_messages = after_json.get("messages") or []
    if not isinstance(before_messages, list) or not isinstance(after_messages, list):
        raise ValueError("ExecutionState.messages must be a list")

    messages_append: list[JsonValue]
    if after_messages[: len(before_messages)] == before_messages:
        messages_append = after_messages[len(before_messages):]
    elif before_messages != after_messages:
        messages_append = []
        after_json["messages"] = after_messages
    else:
        messages_append = []

    variables_set, variables_delete = _build_map_delta(
        _json_map(before_json.get("variables"), "before.variables"),
        _json_map(after_json.get("variables"), "after.variables"),
    )
    tool_results_set, tool_results_delete = _build_map_delta(
        _json_map(before_json.get("tool_results"), "before.tool_results"),
        _json_map(after_json.get("tool_results"), "after.tool_results"),
    )
    nested_states_set, nested_states_delete = _build_map_delta(
        _json_map(before_json.get("nested_states"), "before.nested_states"),
        _json_map(after_json.get("nested_states"), "after.nested_states"),
    )
    child_workflows_set, child_workflows_delete = _build_map_delta(
        _json_map(before_json.get("child_workflows"), "before.child_workflows"),
        _json_map(after_json.get("child_workflows"), "after.child_workflows"),
    )

    fields_set: dict[str, JsonValue] = {}
    fields_unset: list[str] = []
    keys = sorted(set(before_json) | set(after_json))
    for key in keys:
        if key in _SPECIAL_FIELDS:
            continue
        before_value = before_json.get(key)
        after_has_key = key in after_json
        after_value = after_json.get(key)
        if not after_has_key:
            fields_unset.append(key)
            continue
        if before_value != after_value:
            if after_value is None:
                fields_unset.append(key)
            else:
                fields_set[key] = after_value

    if "messages" in after_json and before_messages != after_messages and not messages_append:
        fields_set["messages"] = after_json["messages"]

    return ExecutionStateDelta(
        messages_append=messages_append,
        variables_set=variables_set,
        variables_delete=variables_delete,
        tool_results_set=tool_results_set,
        tool_results_delete=tool_results_delete,
        nested_states_set=nested_states_set,
        nested_states_delete=nested_states_delete,
        child_workflows_set=child_workflows_set,
        child_workflows_delete=child_workflows_delete,
        fields_set=fields_set,
        fields_unset=fields_unset,
    )


def apply_state_delta(
    state: ExecutionState | None,
    delta: ExecutionStateDelta,
) -> ExecutionState:
    """Apply delta and return a validated ExecutionState projection."""
    if state is None:
        data: JsonObject = {}
    else:
        data = _state_json(state)

    if delta.messages_append:
        messages = deepcopy(data.get("messages") or [])
        if not isinstance(messages, list):
            raise ValueError("ExecutionState.messages must be a list")
        messages.extend(deepcopy(delta.messages_append))
        data["messages"] = messages

    for field_name, set_values, delete_keys in (
        ("variables", delta.variables_set, delta.variables_delete),
        ("tool_results", delta.tool_results_set, delta.tool_results_delete),
        ("nested_states", delta.nested_states_set, delta.nested_states_delete),
        ("child_workflows", delta.child_workflows_set, delta.child_workflows_delete),
    ):
        current = _json_map(data.get(field_name), field_name)
        for key in delete_keys:
            _ = current.pop(key, None)
        current.update(deepcopy(set_values))
        data[field_name] = current

    for key in delta.fields_unset:
        if key in ExecutionState.model_fields:
            data[key] = None
        else:
            _ = data.pop(key, None)
    for key, value in delta.fields_set.items():
        data[key] = deepcopy(value)

    return ExecutionState.model_validate(data)

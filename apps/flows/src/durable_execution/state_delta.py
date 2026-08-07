"""Сборка и применение доменных delta для ExecutionState."""

from __future__ import annotations

from copy import deepcopy

from core.state import ExecutionState
from core.state.flow_ui import FlowUIDocument
from core.types import JsonObject, JsonValue, require_json_object

from .models import ExecutionStateDelta, UIClientMutationRef
from .ui_state_delta import (
    apply_ui_document_delta,
    build_ui_document_delta,
    populate_ui_state_fields,
    strip_ui_owned_fields,
)

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


def _merge_ui_delta(target: ExecutionStateDelta, source: ExecutionStateDelta) -> None:
    target.ui_components_upsert = source.ui_components_upsert
    target.ui_components_delete = source.ui_components_delete
    target.ui_component_properties_set = source.ui_component_properties_set
    target.ui_component_properties_delete = source.ui_component_properties_delete
    target.ui_container_layout_set = source.ui_container_layout_set
    target.ui_container_layout_unset = source.ui_container_layout_unset
    target.ui_component_placement_set = source.ui_component_placement_set
    target.ui_component_placement_unset = source.ui_component_placement_unset
    target.ui_data_set = source.ui_data_set
    target.ui_data_delete = source.ui_data_delete
    target.ui_surfaces_upsert = source.ui_surfaces_upsert
    target.ui_surfaces_delete = source.ui_surfaces_delete
    target.ui_pages_upsert = source.ui_pages_upsert
    target.ui_pages_delete = source.ui_pages_delete
    target.ui_active_page_set = source.ui_active_page_set
    target.ui_session_view_state_set = source.ui_session_view_state_set
    target.ui_session_view_state_delete = source.ui_session_view_state_delete
    target.ui_revision_set = source.ui_revision_set


def build_state_delta(
    before: ExecutionState | None,
    after: ExecutionState,
) -> ExecutionStateDelta:
    """Возвращает компактную семантическую delta от before к after."""
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
            if after_value is None and key in ExecutionState.model_fields:
                fields_unset.append(key)
            else:
                fields_set[key] = after_value

    if "messages" in after_json and before_messages != after_messages and not messages_append:
        fields_set["messages"] = after_json["messages"]

    delta = ExecutionStateDelta(
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

    if before.ui_document != after.ui_document:
        strip_ui_owned_fields(delta.fields_set)
        _ = delta.fields_unset[:]
        delta.fields_unset = [
            key for key in delta.fields_unset if key not in {"ui_document", "ui_interaction"}
        ]
        _merge_ui_delta(delta, build_ui_document_delta(before.ui_document, after.ui_document))
        if after.ui_document.last_accepted_client_mutation_id != (
            before.ui_document.last_accepted_client_mutation_id
        ):
            # mutation id on document is synchronized via state fields below
            pass
    else:
        strip_ui_owned_fields(delta.fields_set)

    populate_ui_state_fields(
        delta,
        before_interaction=before.ui_interaction,
        after_interaction=after.ui_interaction,
        before_mutation_id=before.ui_last_accepted_client_mutation_id,
        after_mutation_id=after.ui_last_accepted_client_mutation_id,
        before_mutation_hash=before.ui_last_accepted_client_mutation_hash,
        after_mutation_hash=after.ui_last_accepted_client_mutation_hash,
    )
    strip_ui_owned_fields(delta.fields_set)
    return delta


def apply_state_delta(
    state: ExecutionState | None,
    delta: ExecutionStateDelta,
) -> ExecutionState:
    """Применяет delta и возвращает валидированную проекцию ExecutionState."""
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

    has_ui_semantic = not ExecutionStateDelta(
        ui_components_upsert=delta.ui_components_upsert,
        ui_components_delete=delta.ui_components_delete,
        ui_component_properties_set=delta.ui_component_properties_set,
        ui_component_properties_delete=delta.ui_component_properties_delete,
        ui_container_layout_set=delta.ui_container_layout_set,
        ui_container_layout_unset=delta.ui_container_layout_unset,
        ui_component_placement_set=delta.ui_component_placement_set,
        ui_component_placement_unset=delta.ui_component_placement_unset,
        ui_data_set=delta.ui_data_set,
        ui_data_delete=delta.ui_data_delete,
        ui_surfaces_upsert=delta.ui_surfaces_upsert,
        ui_surfaces_delete=delta.ui_surfaces_delete,
        ui_pages_upsert=delta.ui_pages_upsert,
        ui_pages_delete=delta.ui_pages_delete,
        ui_active_page_set=delta.ui_active_page_set,
        ui_session_view_state_set=delta.ui_session_view_state_set,
        ui_session_view_state_delete=delta.ui_session_view_state_delete,
        ui_revision_set=delta.ui_revision_set,
    ).is_empty()

    if has_ui_semantic:
        raw_document = data.get("ui_document")
        if raw_document is None:
            raise ValueError("Semantic UI delta requires an existing ui_document")
        document = FlowUIDocument.model_validate(raw_document)
        data["ui_document"] = require_json_object(
            apply_ui_document_delta(document, delta).model_dump(mode="json"),
            "ui_document",
        )

    if delta.ui_interaction_unset:
        data["ui_interaction"] = None
    elif delta.ui_interaction_set is not None:
        data["ui_interaction"] = require_json_object(
            delta.ui_interaction_set.model_dump(mode="json"),
            "ui_interaction",
        )

    mutation_ref: UIClientMutationRef | None = delta.ui_last_client_mutation_set
    if mutation_ref is not None:
        data["ui_last_accepted_client_mutation_id"] = mutation_ref.mutation_id
        data["ui_last_accepted_client_mutation_hash"] = mutation_ref.mutation_hash
        document_raw = data.get("ui_document")
        if isinstance(document_raw, dict) and mutation_ref.mutation_id is not None:
            document_raw["last_accepted_client_mutation_id"] = mutation_ref.mutation_id

    return ExecutionState.model_validate(data)

"""Статический data-flow inspector для редактора flows.

Inspector намеренно консервативен: не исполняет пользовательский код и
удалённые вызовы, только читает конфигурацию нод и известные runtime-контракты.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from apps.flows.src.models import (
    DataflowAvailability,
    DataflowCanvasChip,
    DataflowCanvasChipKind,
    DataflowCanvasOutputChip,
    DataflowCanvasSummary,
    DataflowConfidence,
    DataflowConfigRead,
    DataflowConfigRef,
    DataflowInputMappingRow,
    DataflowInspectResult,
    DataflowIssue,
    DataflowMappingSource,
    DataflowNodeInfo,
    DataflowRequiredInput,
    DataflowSeverity,
    DataflowSource,
    DataflowStateDescriptor,
    DataflowStatus,
    Edge,
    FlowVariableConfig,
    GraphNodeConfig,
    TriggerConfig,
)
from core.code_contract import CodeContract, scan_code_contract
from core.models.flow_interface import FlowInterfaceConfig
from core.state.flow_ui_contract import (
    FlowUIContractField,
    iter_flow_ui_submit_contract_fields,
)
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject, JsonValue, require_json_object
from core.variables import scan_prompt_template

SYSTEM_STATE_FIELDS: dict[str, str] = {
    "content": "string|null",
    "response": "string|null",
    "result": "any",
    "validation": "object|null",
    "variables": "object",
    "ui_values": "object",
    "triggers": "object",
    "files": "array",
    "messages": "array",
    "tool_results": "object",
    "execution_exceptions": "array",
    "task_id": "string",
    "context_id": "string",
    "user_id": "string",
    "session_id": "string",
    "branch_id": "string",
    "current_nodes": "array",
}

MAX_STATE_FIELDS_PER_NODE = 220

CANVAS_START_TOP_LEVEL_FIELDS = frozenset({"content", "files"})


def inspect_flow_dataflow(
    *,
    flow_id: str | None,
    branch_id: str,
    entry: str | None,
    nodes: Mapping[str, GraphNodeConfig],
    edges: Sequence[Edge],
    variables: Mapping[str, FlowVariableConfig] | None = None,
    sample_state: JsonObject | None = None,
    observed_runs: JsonObject | None = None,
    triggers: Mapping[str, TriggerConfig] | None = None,
    interface: FlowInterfaceConfig | None = None,
) -> DataflowInspectResult:
    node_payloads: dict[str, JsonObject] = {
        node_id: require_json_object(
            cast(object, node_config.model_dump(mode="json", by_alias=True, exclude_none=True)),
            f"nodes.{node_id}",
        )
        for node_id, node_config in nodes.items()
        if node_id
    }
    edge_list = list(edges)
    normalized_branch_id = branch_id or "default"
    normalized_entry = (
        entry if isinstance(entry, str) and entry else _infer_entry(node_payloads, edge_list)
    )

    normalized_variables = variables or {}
    normalized_triggers = triggers or {}
    ui_contract_fields = _ui_contract_fields(interface)
    sanitized_sample = _sanitize_sample_state_for_inspect(
        sample_state,
        normalized_variables,
        ui_contract_fields,
    )
    seed = _initial_state_map(normalized_variables, sanitized_sample, ui_contract_fields)
    incoming_by_node = _incoming_edges(edge_list)
    outgoing_by_node = _outgoing_edges(edge_list)
    reachable = _reachable_nodes(normalized_entry, outgoing_by_node)

    in_states: dict[str, dict[str, DataflowStateDescriptor]] = {}
    out_states: dict[str, dict[str, DataflowStateDescriptor]] = {}
    node_infos: dict[str, DataflowNodeInfo] = {}

    for _ in range(max(1, min(64, len(node_payloads) * 8 + 8))):
        changed = False
        for node_id, node in node_payloads.items():
            incoming_maps: list[dict[str, DataflowStateDescriptor]] = []
            if node_id == normalized_entry:
                incoming_maps.append(seed)

            for edge in incoming_by_node.get(node_id, []):
                pred_state = out_states.get(edge.from_node)
                if pred_state is None:
                    continue
                incoming_maps.append(_state_for_edge(pred_state, edge))

            if incoming_maps:
                incoming = _merge_state_maps(incoming_maps)
            else:
                incoming = copy.deepcopy(seed)

            observation = (observed_runs or {}).get(node_id)
            info, output_state = _inspect_node(node_id, node, incoming, observation)
            if normalized_entry and node_id not in reachable and node_id != normalized_entry:
                info.issues.append(
                    _issue(
                        "unreachable_node",
                        "info",
                        "Node is not reachable from the branch entry.",
                    )
                )

            if _state_signature(in_states.get(node_id, {})) != _state_signature(incoming):
                in_states[node_id] = incoming
                changed = True
            if _state_signature(out_states.get(node_id, {})) != _state_signature(output_state):
                out_states[node_id] = output_state
                changed = True
            node_infos[node_id] = info
        if not changed:
            break

    for node_id, info in node_infos.items():
        info.incoming_state = _summarize_state_map(in_states.get(node_id, seed))
        info.output_state = _summarize_state_map(
            out_states.get(node_id, in_states.get(node_id, seed))
        )
        info.canvas = _canvas_summary(
            info,
            is_entry=node_id == normalized_entry,
            seed=in_states.get(node_id, seed),
            variables=normalized_variables,
            triggers=normalized_triggers,
            ui_contract_fields=ui_contract_fields,
        )

    return DataflowInspectResult(
        flow_id=flow_id,
        branch_id=normalized_branch_id,
        entry=normalized_entry,
        nodes=node_infos,
        variables=_summarize_state_map(_variable_state_map(variables or {})),
        issues=_graph_issues(normalized_entry, node_payloads),
    )


def _infer_entry(nodes: dict[str, JsonObject], edges: list[Edge]) -> str | None:
    if not nodes:
        return None
    targets = {edge.to_node for edge in edges if edge.to_node}
    for node_id in nodes:
        if node_id not in targets:
            return node_id
    return next(iter(nodes))


def _incoming_edges(edges: list[Edge]) -> dict[str, list[Edge]]:
    out: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        to_node = edge.to_node
        if isinstance(to_node, str) and to_node:
            out[to_node].append(edge)
    return out


def _outgoing_edges(edges: list[Edge]) -> dict[str, list[Edge]]:
    out: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        out[edge.from_node].append(edge)
    return out


def _reachable_nodes(entry: str | None, outgoing_by_node: dict[str, list[Edge]]) -> set[str]:
    if not entry:
        return set()
    seen = {entry}
    q: deque[str] = deque([entry])
    while q:
        node_id = q.popleft()
        for edge in outgoing_by_node.get(node_id, []):
            to_node = edge.to_node
            if not isinstance(to_node, str) or not to_node or to_node in seen:
                continue
            seen.add(to_node)
            q.append(to_node)
    return seen


def _initial_state_map(
    variables: Mapping[str, FlowVariableConfig],
    sample_state: JsonObject,
    ui_contract_fields: tuple[FlowUIContractField, ...] = (),
) -> dict[str, DataflowStateDescriptor]:
    out: dict[str, DataflowStateDescriptor] = {}
    for path, type_name in SYSTEM_STATE_FIELDS.items():
        out[path] = _descriptor(
            path,
            type_name=type_name,
            source="system",
            availability="guaranteed",
            confidence="runtime_contract",
            protected=path in FROZEN_STATE_FIELDS,
        )
    out.update(_variable_state_map(variables))
    out.update(_ui_values_state_map(ui_contract_fields))
    for path, value in _flatten_sample_state_paths(
        sample_state, variables, ui_contract_fields
    ).items():
        existing = out.get(path)
        desc = _descriptor(
            path,
            type_name=_type_of_value(value),
            source="preview_state",
            availability="observed",
            confidence="sample",
            sample_value=_sample_value(value),
            protected=_top_path(path) in FROZEN_STATE_FIELDS,
        )
        out[path] = _merge_descriptor(existing, desc) if existing else desc
    return out


def _is_system_descriptor(desc: DataflowStateDescriptor) -> bool:
    return "system" in set(_as_list(desc.source))


def _sanitize_sample_state_for_inspect(
    sample_state: JsonObject | None,
    variables: Mapping[str, FlowVariableConfig],
    ui_contract_fields: tuple[FlowUIContractField, ...] = (),
) -> JsonObject:
    if not sample_state:
        return {}
    out: JsonObject = {}
    if "content" in sample_state:
        out["content"] = sample_state["content"]
    if "files" in sample_state:
        out["files"] = sample_state["files"]
    raw_variables = sample_state.get("variables")
    if isinstance(raw_variables, dict):
        variables_obj = require_json_object(raw_variables, "sample_state.variables")
        trimmed_variables: JsonObject = {}
        for key in variables:
            if key in variables_obj:
                trimmed_variables[key] = variables_obj[key]
        if trimmed_variables:
            out["variables"] = trimmed_variables
    raw_ui_values = sample_state.get("ui_values")
    if isinstance(raw_ui_values, dict):
        ui_values_obj = require_json_object(raw_ui_values, "sample_state.ui_values")
        known_fields = {field.field for field in ui_contract_fields}
        trimmed_ui_values: JsonObject = {}
        for key in known_fields:
            if key in ui_values_obj:
                trimmed_ui_values[key] = ui_values_obj[key]
        if trimmed_ui_values:
            out["ui_values"] = trimmed_ui_values
    return out


def _flatten_sample_state_paths(
    sample_state: JsonObject,
    variables: Mapping[str, FlowVariableConfig],
    ui_contract_fields: tuple[FlowUIContractField, ...] = (),
) -> dict[str, JsonValue]:
    sanitized = _sanitize_sample_state_for_inspect(
        sample_state, variables, ui_contract_fields
    )
    out: dict[str, JsonValue] = {}
    known_ui_fields = {field.field for field in ui_contract_fields}
    for top_key, value in sanitized.items():
        if top_key in CANVAS_START_TOP_LEVEL_FIELDS:
            out[top_key] = value
            continue
        if top_key == "variables" and isinstance(value, dict):
            variables_obj = require_json_object(value, "variables")
            for var_key in variables:
                if var_key in variables_obj:
                    out[f"variables.{var_key}"] = variables_obj[var_key]
            continue
        if top_key == "ui_values" and isinstance(value, dict):
            ui_values_obj = require_json_object(value, "ui_values")
            for field_key in known_ui_fields:
                if field_key in ui_values_obj:
                    out[f"ui_values.{field_key}"] = ui_values_obj[field_key]
    return out


def _chip_kind_for_path(path: str) -> DataflowCanvasChipKind:
    if path == "files":
        return "files"
    if path.startswith("variables."):
        return "variable"
    if path.startswith("triggers."):
        return "trigger"
    if path.startswith("ui_values."):
        return "ui_value"
    return "content"


def _build_entry_canvas_inputs(
    seed: dict[str, DataflowStateDescriptor],
    variables: Mapping[str, FlowVariableConfig],
    triggers: Mapping[str, TriggerConfig],
    ui_contract_fields: tuple[FlowUIContractField, ...] = (),
) -> list[DataflowCanvasChip]:
    chips: list[DataflowCanvasChip] = []
    seen_labels: set[str] = set()

    def add_chip(
        label: str,
        *,
        type_name: str = "any",
        required: bool = False,
    ) -> None:
        if not label or label in seen_labels:
            return
        seen_labels.add(label)
        descriptor = seed.get(label)
        chips.append(
            DataflowCanvasChip(
                label=label,
                target=label,
                status="ok",
                type=descriptor.type if descriptor else type_name,
                required=required,
                kind=_chip_kind_for_path(label),
            )
        )

    content_descriptor = seed.get("content")
    add_chip("content", type_name=content_descriptor.type if content_descriptor else "string|null")

    files_descriptor = seed.get("files")
    if files_descriptor is not None and "preview_state" in set(_as_list(files_descriptor.source)):
        add_chip("files", type_name=files_descriptor.type)

    for key in sorted(variables):
        if not key:
            continue
        path = f"variables.{key}"
        descriptor = seed.get(path)
        add_chip(path, type_name=descriptor.type if descriptor else "any")

    for field in sorted(ui_contract_fields, key=lambda item: item.field):
        if not field.field:
            continue
        path = f"ui_values.{field.field}"
        descriptor = seed.get(path)
        add_chip(path, type_name=descriptor.type if descriptor else _type_of_value(field.value))

    for trigger_id, trigger in sorted(triggers.items()):
        if not trigger.enabled:
            continue
        output_mapping = trigger.output_mapping
        for state_key in output_mapping:
            if state_key == "content":
                add_chip("content", type_name=content_descriptor.type if content_descriptor else "string|null")
            elif state_key == "context":
                add_chip(f"triggers.{trigger_id}.context", type_name="object")
            elif state_key.startswith("context."):
                context_key = state_key[len("context.") :]
                add_chip(f"triggers.{trigger_id}.context.{context_key}", type_name="any")
        add_chip(f"triggers.{trigger_id}.payload", type_name="object")

    return chips


def _ui_contract_fields(
    interface: FlowInterfaceConfig | None,
) -> tuple[FlowUIContractField, ...]:
    if interface is None:
        return ()
    return iter_flow_ui_submit_contract_fields(interface.template.document)


def _ui_values_state_map(
    ui_contract_fields: tuple[FlowUIContractField, ...],
) -> dict[str, DataflowStateDescriptor]:
    out: dict[str, DataflowStateDescriptor] = {}
    for field in ui_contract_fields:
        if not field.field:
            continue
        path = f"ui_values.{field.field}"
        out[path] = _descriptor(
            path,
            type_name=_type_of_value(field.value),
            source="flow_ui_contract",
            availability="guaranteed",
            confidence="runtime_contract",
            sample_value=_sample_value(field.value),
        )
    return out


def _variable_state_map(
    variables: Mapping[str, FlowVariableConfig],
) -> dict[str, DataflowStateDescriptor]:
    out: dict[str, DataflowStateDescriptor] = {}
    for key, variable in variables.items():
        if not key:
            continue
        value = variable.value
        secret = variable.secret
        path = f"variables.{key}"
        out[path] = _descriptor(
            path,
            type_name=_type_of_value(value),
            source="flow_variable",
            availability="guaranteed",
            confidence="declared",
            sample_value="<secret>" if secret else _sample_value(value),
        )
    return out


def _state_for_edge(
    state_map: dict[str, DataflowStateDescriptor], edge: Edge
) -> dict[str, DataflowStateDescriptor]:
    conditioned = edge.condition is not None
    contributes = edge.contributes_to_join is not False
    if not conditioned and contributes:
        return copy.deepcopy(state_map)
    out = copy.deepcopy(state_map)
    for desc in out.values():
        if conditioned and desc.availability == "guaranteed":
            desc.availability = "maybe"
        if not contributes:
            desc.join_contribution = "non_join"
    return out


def _merge_state_maps(
    maps: list[dict[str, DataflowStateDescriptor]],
) -> dict[str, DataflowStateDescriptor]:
    if not maps:
        return {}
    total = len(maps)
    all_paths = sorted({path for m in maps for path in m})
    out: dict[str, DataflowStateDescriptor] = {}
    for path in all_paths:
        present = [m[path] for m in maps if path in m]
        merged: DataflowStateDescriptor | None = None
        for desc in present:
            merged = _merge_descriptor(merged, desc) if merged else copy.deepcopy(desc)
        if merged is None:
            continue
        if len(present) < total and merged.availability == "guaranteed":
            merged.availability = "maybe"
        out[path] = merged
    return out


def _inspect_node(
    node_id: str,
    node: JsonObject,
    incoming: dict[str, DataflowStateDescriptor],
    observation: JsonValue = None,
) -> tuple[DataflowNodeInfo, dict[str, DataflowStateDescriptor]]:
    issues: list[DataflowIssue] = []
    input_rows = _inspect_input_mapping(node, incoming, issues)
    required_inputs = _derive_required_inputs(node, incoming, input_rows, issues)
    reads = _merge_config_reads(
        _inspect_config_reads(node, incoming, issues),
        _inspect_code_reads(node, incoming, issues),
        _inspect_reflection_reads(node, incoming),
    )
    writes = _infer_node_writes(node_id, node, issues)
    observed_writes = _observed_writes(node_id, observation)
    writes = _dedupe_descriptors([*writes, *observed_writes])
    output = copy.deepcopy(incoming)
    for desc in writes:
        path = desc.path
        existing = output.get(path)
        output[path] = _merge_descriptor(existing, desc) if existing else copy.deepcopy(desc)
    observed_at: JsonValue = None
    if isinstance(observation, dict):
        observation_obj = require_json_object(observation, "observation")
        observed_at = observation_obj.get("observed_at")
    info = DataflowNodeInfo(
        node_id=node_id,
        node_type=str(node.get("type") or ""),
        input_mapping=input_rows,
        required_inputs=required_inputs,
        reads=reads,
        writes=writes,
        observed_writes=observed_writes,
        observed_at=observed_at,
        result_keys=_infer_result_keys(node, observation),
        issues=issues,
    )
    return info, output


def _infer_result_keys(node: JsonObject, observation: JsonValue = None) -> list[str]:
    keys: set[str] = set()
    keys.update(_schema_properties(node.get("output_schema")).keys())
    keys.update(_infer_code_return_keys(node))
    output_mapping = node.get("output_mapping")
    if isinstance(output_mapping, dict):
        keys.update(key for key in output_mapping if key)
    state_mapping = node.get("state_mapping")
    if isinstance(state_mapping, dict):
        keys.update(key for key in state_mapping if key)
    if isinstance(observation, dict):
        observation_obj = require_json_object(observation, "observation")
        output_state = observation_obj.get("output_state")
        if isinstance(output_state, dict):
            output_state_obj = require_json_object(output_state, "observation.output_state")
            result = output_state_obj.get("result")
            if isinstance(result, dict):
                result_obj = require_json_object(result, "observation.output_state.result")
                keys.update(key for key in result_obj if key)
            api_response = output_state_obj.get("api_response")
            if isinstance(api_response, dict):
                api_response_obj = require_json_object(
                    api_response, "observation.output_state.api_response"
                )
                keys.update(key for key in api_response_obj if key)
    node_type = str(node.get("type") or "")
    if node_type in {"llm_node", "flow", "remote_flow", "hitl_node"}:
        keys.add("response")
    if node_type in {
        "code",
        "external_api",
        "mcp",
        "datasource",
        "channel",
        "flow",
        "remote_flow",
    }:
        keys.add("result")
    return sorted(keys)


def _inspect_input_mapping(
    node: JsonObject,
    incoming: dict[str, DataflowStateDescriptor],
    issues: list[DataflowIssue],
) -> list[DataflowInputMappingRow]:
    mapping = node.get("input_mapping")
    if not isinstance(mapping, dict):
        return []
    mapping_obj = require_json_object(mapping, "input_mapping")
    rows: list[DataflowInputMappingRow] = []
    for target, raw_source in mapping_obj.items():
        if not target:
            continue
        source = "" if raw_source is None else str(raw_source)
        parsed = _parse_mapping_source(source)
        row = DataflowInputMappingRow(
            target=target,
            source=source,
            source_kind=parsed.kind,
            source_path=parsed.path,
            status="ok",
            type="any",
        )
        if parsed.kind == "state":
            path = parsed.path or ""
            desc = incoming.get(path)
            if desc is None:
                row.status = "missing"
                issues.append(
                    _issue(
                        "missing_state_path",
                        "warning",
                        f"Input mapping reads @state:{path}, but that field is not produced before this node.",
                        path=path,
                        target=target,
                    )
                )
            else:
                row.type = desc.type
                row.producers = desc.producers
                row.sample_value = desc.sample_value
        elif parsed.kind == "var":
            path = f"variables.{parsed.path}"
            desc = incoming.get(path)
            if desc is None:
                row.status = "missing"
                issues.append(
                    _issue(
                        "missing_variable",
                        "warning",
                        f"Input mapping reads @var:{parsed.path}, but this variable is not declared in the branch.",
                        path=str(parsed.path),
                        target=target,
                    )
                )
            else:
                row.type = desc.type
                row.sample_value = desc.sample_value
        else:
            row.type = _type_of_literal(source)
            row.sample_value = _sample_value(source)
        rows.append(row)
    return rows


def _input_mapping_targets(input_rows: list[DataflowInputMappingRow]) -> dict[str, str]:
    return {row.target: row.source for row in input_rows if row.target}


def _input_satisfied_by_state(
    name: str, incoming: dict[str, DataflowStateDescriptor]
) -> bool:
    return name in incoming or f"variables.{name}" in incoming


def _prompt_variable_available(
    name: str, incoming: dict[str, DataflowStateDescriptor]
) -> bool:
    """Prompt placeholders: state.variables.* and Flow UI ui_values.*."""
    if f"variables.{name}" in incoming:
        return True
    if name == "ui_values":
        if "ui_values" in incoming:
            return True
        return any(path.startswith("ui_values.") for path in incoming)
    return False


def _derive_required_inputs(
    node: JsonObject,
    incoming: dict[str, DataflowStateDescriptor],
    input_rows: list[DataflowInputMappingRow],
    issues: list[DataflowIssue],
) -> list[DataflowRequiredInput]:
    """Строит контракт обязательных входов ноды.

    Приоритет: явный ``input_schema`` (ручной контракт) → per-type вывод
    (``parameters_schema`` для code, prompt-переменные для llm_node).
    Все несоответствия — advisory issues, они не блокируют сохранение.
    """

    node_type = str(node.get("type") or "")
    mapped_targets = _input_mapping_targets(input_rows)
    local_variables = node.get("local_variables")
    local_keys: set[str] = (
        set(require_json_object(local_variables, "local_variables"))
        if isinstance(local_variables, dict)
        else set()
    )
    required: list[DataflowRequiredInput] = []

    input_schema = node.get("input_schema")
    if isinstance(input_schema, dict):
        schema_obj = require_json_object(input_schema, "input_schema")
        props = _schema_properties(schema_obj)
        for name in _schema_required_names(schema_obj):
            prop = props.get(name)
            satisfied = (
                name in mapped_targets
                or _input_satisfied_by_state(name, incoming)
                or _schema_has_default(prop)
            )
            source = mapped_targets.get(name)
            required.append(
                DataflowRequiredInput(
                    name=name,
                    origin="contract",
                    type=_schema_type(prop),
                    satisfied=satisfied,
                    source=source,
                )
            )
            if not satisfied:
                issues.append(
                    _issue(
                        "missing_required_input",
                        "error",
                        f"Required input '{name}' (declared in input_schema) is not mapped and not available before this node.",
                        target=name,
                    )
                )
        return required

    if node_type == "code":
        params_schema = node.get("parameters_schema")
        if isinstance(params_schema, dict):
            schema_obj = require_json_object(params_schema, "parameters_schema")
            props = _schema_properties(schema_obj)
            for name in _schema_required_names(schema_obj):
                prop = props.get(name)
                satisfied = name in mapped_targets or _schema_has_default(prop)
                source = mapped_targets.get(name)
                required.append(
                    DataflowRequiredInput(
                        name=name,
                        origin="parameters_schema",
                        type=_schema_type(prop),
                        satisfied=satisfied,
                        source=source,
                    )
                )
                if not satisfied:
                    issues.append(
                        _issue(
                            "missing_required_input",
                            "error",
                            f"Required code argument '{name}' is not provided via input_mapping and has no default.",
                            target=name,
                        )
                    )
        return required

    if node_type == "llm_node":
        prompt = node.get("prompt")
        scan = scan_prompt_template(prompt if isinstance(prompt, str) else None)
        for root in scan.required_roots:
            satisfied = (
                root in local_keys
                or root in mapped_targets
                or _prompt_variable_available(root, incoming)
            )
            source = mapped_targets.get(root)
            required.append(
                DataflowRequiredInput(
                    name=root,
                    origin="prompt",
                    type="any",
                    satisfied=satisfied,
                    source=source,
                )
            )
            if not satisfied:
                issues.append(
                    _issue(
                        "unknown_prompt_variable",
                        "warning",
                        f"Prompt uses {{{root}}}, but that variable is not declared as a flow/local variable and is not produced before this node.",
                        target=root,
                    )
                )
        return required

    if node_type == "reflection":
        target_path = _reflection_target_state_path(node)
        if target_path is None:
            return required
        desc = incoming.get(target_path)
        satisfied = (
            desc is not None
            and desc.availability == "guaranteed"
            and len(desc.producers) > 0
        )
        required.append(
            DataflowRequiredInput(
                name=target_path,
                origin="contract",
                type=desc.type if desc is not None else "any",
                satisfied=satisfied,
                source=desc.producers[0] if satisfied and desc is not None else None,
            )
        )
        if not satisfied:
            issues.append(
                _issue(
                    "reflection_target_unavailable",
                    "error",
                    (
                        f"Reflection target '{target_path}' is not guaranteed available "
                        "before this node (no upstream producer, or only maybe on some paths)."
                    ),
                    path=target_path,
                    target=target_path,
                )
            )
        return required

    if node_type == "channel" and node.get("channel") == "email":
        for name, origin_note in (
            ("recipient", "email.to"),
            ("text", "email.body"),
        ):
            satisfied = name in mapped_targets
            source = mapped_targets.get(name)
            required.append(
                DataflowRequiredInput(
                    name=name,
                    origin="contract",
                    type="string",
                    satisfied=satisfied,
                    source=source,
                )
            )
            if not satisfied:
                issues.append(
                    _issue(
                        "missing_required_input",
                        "error",
                        (
                            f"Email channel requires input_mapping.{name} "
                            f"({origin_note}) before send."
                        ),
                        target=name,
                    )
                )
        subject_satisfied = "subject" in mapped_targets
        required.append(
            DataflowRequiredInput(
                name="subject",
                origin="contract",
                type="string",
                satisfied=subject_satisfied,
                source=mapped_targets.get("subject"),
            )
        )
        if not subject_satisfied:
            issues.append(
                _issue(
                    "missing_optional_input",
                    "warning",
                    "Email channel: map input_mapping.subject (empty string allowed).",
                    target="subject",
                )
            )
        return required

    return required


def _reflection_target_state_path(node: JsonObject) -> str | None:
    """State path, который reflection читает из critic_policy.target."""
    raw_policy = node.get("critic_policy")
    if not isinstance(raw_policy, dict):
        return None
    raw_target = raw_policy.get("target")
    if not isinstance(raw_target, dict):
        return None
    kind = raw_target.get("kind")
    if kind in {"response", "result", "validation"}:
        return str(kind)
    if kind == "state_path":
        state_path = raw_target.get("state_path")
        if isinstance(state_path, str) and state_path.strip() != "":
            return state_path
    return None


def _schema_required_names(schema: JsonObject) -> list[str]:
    raw = schema.get("required")
    if not isinstance(raw, list):
        return []
    return [name for name in raw if isinstance(name, str) and name]


def _schema_has_default(schema: JsonValue) -> bool:
    return isinstance(schema, dict) and "default" in require_json_object(schema, "schema")


def _inspect_config_reads(
    node: JsonObject,
    incoming: dict[str, DataflowStateDescriptor],
    issues: list[DataflowIssue],
) -> list[DataflowConfigRead]:
    refs: list[DataflowConfigRef] = []
    for field in ("url", "body_template", "headers", "channel_config"):
        if field in node:
            refs.extend(_find_mapping_refs(node[field], field))
    reads: list[DataflowConfigRead] = []
    for ref in refs:
        kind = ref.kind
        path = ref.path
        lookup = path if kind == "state" else f"variables.{path}"
        desc = incoming.get(lookup)
        status: DataflowStatus = "ok" if desc else "missing"
        reads.append(
            DataflowConfigRead(
                source_kind=kind,
                source_path=path,
                config_path=ref.config_path,
                status=status,
                type=desc.type if desc else "any",
            )
        )
        if status == "missing":
            issues.append(
                _issue(
                    f"missing_{kind}_path",
                    "warning",
                    f"Config field {ref.config_path} reads @{kind}:{path}, but it is not available before this node.",
                    path=path,
                )
            )
    return reads


def _inspect_reflection_reads(
    node: JsonObject,
    incoming: dict[str, DataflowStateDescriptor],
) -> list[DataflowConfigRead]:
    if str(node.get("type") or "") != "reflection":
        return []
    target_path = _reflection_target_state_path(node)
    if target_path is None:
        return []
    desc = incoming.get(target_path)
    status: DataflowStatus = (
        "ok"
        if desc is not None
        and desc.availability == "guaranteed"
        and len(desc.producers) > 0
        else "missing"
    )
    return [
        DataflowConfigRead(
            source_kind="state",
            source_path=target_path,
            config_path="critic_policy.target",
            status=status,
            type=desc.type if desc is not None else "any",
        )
    ]


def _inspect_code_reads(
    node: JsonObject,
    incoming: dict[str, DataflowStateDescriptor],
    issues: list[DataflowIssue],
) -> list[DataflowConfigRead]:
    if str(node.get("type") or "") != "code":
        return []
    contract = _code_contract_for_node(node)
    reads: list[DataflowConfigRead] = []
    for path in contract.reads:
        if not path:
            continue
        desc = incoming.get(path)
        status: DataflowStatus = "ok" if desc else "missing"
        reads.append(
            DataflowConfigRead(
                source_kind="state",
                source_path=path,
                config_path=f"code.run.{path}",
                status=status,
                type=desc.type if desc else "any",
            )
        )
        if status == "missing":
            issues.append(
                _issue(
                    "missing_state_path",
                    "warning",
                    f"Code reads state.{path}, but that field is not produced before this node.",
                    path=path,
                )
            )
    for path in contract.optional_reads:
        if not path:
            continue
        desc = incoming.get(path)
        reads.append(
            DataflowConfigRead(
                source_kind="state",
                source_path=path,
                config_path=f"code.run.{path}",
                status="ok",
                type=desc.type if desc else "any",
            )
        )
    return reads


def _merge_config_reads(
    *read_groups: list[DataflowConfigRead],
) -> list[DataflowConfigRead]:
    seen_state_paths: set[str] = set()
    merged: list[DataflowConfigRead] = []
    for group in read_groups:
        for read in group:
            if read.source_kind == "state" and read.source_path:
                if read.source_path in seen_state_paths:
                    continue
                seen_state_paths.add(read.source_path)
            merged.append(read)
    return merged


def _infer_node_writes(
    node_id: str,
    node: JsonObject,
    issues: list[DataflowIssue],
) -> list[DataflowStateDescriptor]:
    node_type = str(node.get("type") or "")
    writes: list[DataflowStateDescriptor] = []

    def add(
        path: str,
        type_name: str = "any",
        source: str = "runtime",
        confidence: DataflowConfidence = "runtime_contract",
    ) -> None:
        if not path:
            return
        desc = _descriptor(
            path,
            type_name=type_name,
            source=source,
            availability="guaranteed",
            confidence=confidence,
            producers=[node_id],
            protected=_top_path(path) in FROZEN_STATE_FIELDS,
        )
        writes.append(desc)
        _append_write_issues(path, source, issues)

    # Общий контракт маппинга BaseNode.
    raw_output_mapping = node.get("output_mapping")
    output_mapping = (
        require_json_object(raw_output_mapping, "output_mapping")
        if isinstance(raw_output_mapping, dict)
        else {}
    )
    schema_props = _schema_properties(node.get("output_schema"))
    return_keys = _infer_code_return_keys(node)
    if output_mapping:
        for result_key, state_field in output_mapping.items():
            if isinstance(state_field, str):
                add(
                    state_field,
                    type_name=_schema_type(schema_props.get(result_key)),
                    source=f"output_mapping.{result_key}",
                    confidence="declared",
                )
    elif schema_props:
        for result_key, prop_schema in schema_props.items():
            add(
                result_key,
                type_name=_schema_type(prop_schema),
                source="output_schema",
                confidence="declared",
            )

    if node_type == "llm_node":
        add("response", "string", source="llm.response")
        if bool(node.get("structured_output")) and schema_props:
            for key, prop_schema in schema_props.items():
                if not output_mapping:
                    add(
                        key,
                        type_name=_schema_type(prop_schema),
                        source="structured_output",
                        confidence="declared",
                    )
        tools = node.get("tools")
        if isinstance(tools, list) and tools:
            add("tool_results", "object", source="llm.tools")
            writes.extend(_infer_llm_tool_writes(node_id, tools, issues))
            issues.append(
                _issue(
                    "llm_tools_dynamic_state",
                    "info",
                    "LLM tools can mutate state dynamically; inspect individual tools for exact fields.",
                )
            )
    elif node_type == "code":
        contract = _code_contract_for_node(node)
        direct_fields = set(contract.writes)
        for field in direct_fields:
            add(field, source="code.state_assignment", confidence="inferred_code")
        for key in contract.variable_writes:
            add(
                f"variables.{key}",
                source="code.variables_assignment",
                confidence="inferred_code",
            )
        if output_mapping:
            pass
        elif return_keys:
            for key in return_keys:
                add(key, source="code.return", confidence="inferred_code")
        else:
            add("result", source="code.return", confidence="dynamic")
            issues.append(
                _issue(
                    "code_return_dynamic",
                    "info",
                    "Code return shape is dynamic or could not be inferred statically.",
                )
            )
    elif node_type == "external_api":
        raw_state_mapping = node.get("state_mapping")
        state_mapping = (
            require_json_object(raw_state_mapping, "state_mapping")
            if isinstance(raw_state_mapping, dict)
            else {}
        )
        for response_field, state_field in state_mapping.items():
            if isinstance(state_field, str):
                add(state_field, source=f"state_mapping.{response_field}", confidence="declared")
        add("api_response", "any", source="external_api.response")
        add("api_status", "string", source="external_api.status")
        add("result", "any", source="external_api.response")
        if not output_mapping:
            issues.append(
                _issue(
                    "external_api_response_dynamic",
                    "info",
                    "External API data may be a JSON object; without output_mapping its keys can be copied to state by BaseNode.",
                )
            )
    elif node_type == "mcp":
        raw_state_mapping = node.get("state_mapping")
        state_mapping = (
            require_json_object(raw_state_mapping, "state_mapping")
            if isinstance(raw_state_mapping, dict)
            else {}
        )
        for _response_field, state_field in state_mapping.items():
            if isinstance(state_field, str):
                add(state_field, "string", source="state_mapping", confidence="declared")
        add("mcp_result", "string", source="mcp.result")
        add("result", "string", source="mcp.result")
    elif node_type == "datasource":
        raw_state_mapping = node.get("state_mapping")
        state_mapping = (
            require_json_object(raw_state_mapping, "state_mapping")
            if isinstance(raw_state_mapping, dict)
            else {}
        )
        for _response_field, state_field in state_mapping.items():
            if isinstance(state_field, str):
                add(state_field, "any", source="state_mapping", confidence="declared")
        add("datasource_result", "any", source="datasource.result")
        add("result", "any", source="datasource.result")
    elif node_type == "channel":
        add("channel_result", "any", source="channel.result")
        add("result", "any", source="channel.result")
        if not output_mapping:
            issues.append(
                _issue(
                    "channel_result_dynamic",
                    "info",
                    "Channel handlers can return objects; without output_mapping their keys may be copied to state by BaseNode.",
                )
            )
    elif node_type == "flow":
        add("response", "string|null", source="nested_flow.response")
        add("result", "any", source="nested_flow.result")
        nested = node.get("__dataflow_nested")
        if isinstance(nested, dict) and isinstance(
            require_json_object(nested, "__dataflow_nested").get("nodes"), dict
        ):
            nested_obj = require_json_object(nested, "__dataflow_nested")
            nested_writes = _nested_flow_writes(node_id, node, nested_obj)
            writes.extend(nested_writes)
            if nested_writes:
                issues.append(
                    _issue(
                        "nested_flow_static_expanded",
                        "info",
                        "Nested flow state writes are expanded from the referenced graph.",
                    )
                )
        else:
            issues.append(
                _issue(
                    "nested_flow_state_dynamic",
                    "info",
                    "Nested flow copies its returned state back to the parent; exact fields depend on the nested graph.",
                )
            )
    elif node_type == "remote_flow":
        add("response", "string|null", source="remote_flow.response")
        add("remote_status", "string", source="remote_flow.status")
        add("result", "any", source="remote_flow.response")
    elif node_type == "hitl_node":
        add("response", "string|null", source="hitl.resume")
        issues.append(
            _issue(
                "hitl_interrupt",
                "info",
                "Initial HITL execution interrupts the graph; response is written after operator resume.",
            )
        )
    elif node_type == "reflection":
        add("validation", "object", source="reflection.gate")
        add("reflection_history", "array", source="reflection.history")
    elif node_type == "resource":
        pass
    elif output_mapping or schema_props:
        pass
    else:
        add("result", "any", source="node.result", confidence="dynamic")

    return _dedupe_descriptors(writes)


def _observed_writes(node_id: str, observation: JsonValue) -> list[DataflowStateDescriptor]:
    if not isinstance(observation, dict):
        return []
    observation_obj = require_json_object(observation, "observation")
    diff = observation_obj.get("diff")
    if not isinstance(diff, list):
        return []
    writes: list[DataflowStateDescriptor] = []
    for item in diff:
        if not isinstance(item, dict):
            continue
        item_obj = require_json_object(item, "observation.diff[]")
        path = item_obj.get("path")
        if not isinstance(path, str) or not path:
            continue
        if item_obj.get("change_type") == "removed":
            value = None
        else:
            value = item_obj.get("new_value")
        writes.append(
            _descriptor(
                path,
                type_name=_type_of_value(value),
                source="observed_run",
                availability="observed",
                confidence="observed",
                producers=[node_id],
                sample_value=_sample_value(value),
                protected=_top_path(path) in FROZEN_STATE_FIELDS,
            )
        )
    return _dedupe_descriptors(writes)


def _infer_llm_tool_writes(
    node_id: str,
    tools: list[JsonValue],
    issues: list[DataflowIssue],
) -> list[DataflowStateDescriptor]:
    writes: list[DataflowStateDescriptor] = []
    for idx, raw_tool in enumerate(tools):
        if isinstance(raw_tool, str):
            tool_name = raw_tool
            writes.append(
                _descriptor(
                    f"tool_results.{tool_name}",
                    type_name="any",
                    source="llm.tool_result",
                    availability="maybe",
                    confidence="runtime_contract",
                    producers=[node_id],
                )
            )
            continue
        if not isinstance(raw_tool, dict):
            continue
        raw_tool_obj = require_json_object(raw_tool, "tool")
        tool_name = _tool_display_id(raw_tool_obj, idx)
        writes.append(
            _descriptor(
                f"tool_results.{tool_name}",
                type_name="any",
                source="llm.tool_result",
                availability="maybe",
                confidence="runtime_contract",
                producers=[node_id],
            )
        )
        code = raw_tool_obj.get("code")
        if isinstance(code, str) and code.strip():
            for path in sorted(_infer_code_state_writes(raw_tool_obj)):
                writes.append(
                    _descriptor(
                        path,
                        type_name="any",
                        source=f"tool.{tool_name}.state_assignment",
                        availability="maybe",
                        confidence="inferred_code",
                        producers=[node_id],
                        protected=_top_path(path) in FROZEN_STATE_FIELDS,
                    )
                )
                _append_write_issues(path, f"tool.{tool_name}.state_assignment", issues)
        tool_type = str(raw_tool_obj.get("type") or "")
        if tool_type in {"flow", "llm_node"} and not raw_tool_obj.get("code"):
            issues.append(
                _issue(
                    "llm_tool_dynamic_state",
                    "info",
                    f"Tool '{tool_name}' can mutate state depending on runtime execution.",
                )
            )
    return _dedupe_descriptors(writes)


def _nested_flow_writes(
    node_id: str, node: JsonObject, nested: JsonObject
) -> list[DataflowStateDescriptor]:
    flow_id = str(node.get("flow_id") or "nested")
    writes: list[DataflowStateDescriptor] = []
    nested_nodes = nested.get("nodes")
    if not isinstance(nested_nodes, dict):
        return writes
    nested_nodes_obj = require_json_object(nested_nodes, "nested.nodes")
    for nested_info in nested_nodes_obj.values():
        if not isinstance(nested_info, dict):
            continue
        nested_info_obj = require_json_object(nested_info, "nested.nodes[]")
        raw_writes = nested_info_obj.get("writes")
        if not isinstance(raw_writes, list):
            continue
        for nested_write in raw_writes:
            if not isinstance(nested_write, dict):
                continue
            nested_write_obj = require_json_object(nested_write, "nested.nodes[].writes[]")
            path = nested_write_obj.get("path")
            if not isinstance(path, str) or not path:
                continue
            writes.append(
                _descriptor(
                    path,
                    type_name=str(nested_write_obj.get("type") or "any"),
                    source=f"nested_flow.{flow_id}",
                    availability="maybe",
                    confidence="nested_static",
                    producers=[node_id],
                    sample_value=nested_write_obj.get("sample_value"),
                    protected=_top_path(path) in FROZEN_STATE_FIELDS,
                )
            )
    return _dedupe_descriptors(writes)


def _tool_display_id(tool: JsonObject, idx: int) -> str:
    for key in ("tool_id", "name", "function", "mcp_tool_name", "tool_name"):
        value = tool.get(key)
        if isinstance(value, str) and value:
            return value
    return f"tool_{idx + 1}"


def _append_write_issues(path: str, source: str, issues: list[DataflowIssue]) -> None:
    top = _top_path(path)
    if top in FROZEN_STATE_FIELDS:
        issues.append(
            _issue(
                "frozen_state_write",
                "error",
                f"{source} writes frozen state field '{path}'. Runtime may reject or make this field unsafe to rely on.",
                path=path,
            )
        )
    if "." in path and source.startswith(("output_mapping", "state_mapping")):
        issues.append(
            _issue(
                "nested_mapping_path_runtime",
                "warning",
                f"{source} targets '{path}'. Runtime writes mapping targets as a top-level state attribute, not as a nested path.",
                path=path,
            )
        )


def _code_contract_for_node(node: JsonObject) -> CodeContract:
    code = node.get("code")
    if not isinstance(code, str) or not code.strip():
        return CodeContract(
            reads=[],
            optional_reads=[],
            writes=[],
            variable_writes=[],
            return_keys=[],
        )
    language = str(node.get("language") or "python")
    return scan_code_contract(language, code)


def _infer_code_state_writes(node: JsonObject) -> set[str]:
    return set(_code_contract_for_node(node).writes)


def _infer_code_return_keys(node: JsonObject) -> set[str]:
    return set(_code_contract_for_node(node).return_keys)


def _schema_properties(schema: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(schema, dict):
        return {}
    schema_obj = require_json_object(schema, "schema")
    props = schema_obj.get("properties")
    if isinstance(props, dict):
        return require_json_object(props, "schema.properties")
    return {}


def _schema_type(schema: JsonValue) -> str:
    if not isinstance(schema, dict):
        return "any"
    schema_obj = require_json_object(schema, "schema")
    type_value = schema_obj.get("type")
    if isinstance(type_value, list):
        return "|".join(str(item) for item in type_value)
    if isinstance(type_value, str) and type_value:
        return type_value
    if "properties" in schema_obj:
        return "object"
    if "items" in schema_obj:
        return "array"
    return "any"


def _parse_mapping_source(source: str) -> DataflowMappingSource:
    if source.startswith("@state:"):
        return DataflowMappingSource(kind="state", path=source[len("@state:") :])
    if source.startswith("@var:"):
        return DataflowMappingSource(kind="var", path=source[len("@var:") :])
    return DataflowMappingSource(kind="const")


def _find_mapping_refs(value: JsonValue, config_path: str) -> list[DataflowConfigRef]:
    refs: list[DataflowConfigRef] = []
    if isinstance(value, str):
        matches = cast(
            list[tuple[Literal["state", "var"], str]],
            re.findall(r"@(state|var):([A-Za-z0-9_.\-\[\]]+)", value),
        )
        for kind, path in matches:
            refs.append(DataflowConfigRef(kind=kind, path=path, config_path=config_path))
    elif isinstance(value, dict):
        value_obj = require_json_object(value, config_path)
        for key, item in value_obj.items():
            refs.extend(_find_mapping_refs(item, f"{config_path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            refs.extend(_find_mapping_refs(item, f"{config_path}[{idx}]"))
    return refs


def _descriptor(
    path: str,
    *,
    type_name: str,
    source: str,
    availability: DataflowAvailability,
    confidence: DataflowConfidence,
    producers: list[str] | None = None,
    sample_value: JsonValue = None,
    protected: bool = False,
) -> DataflowStateDescriptor:
    return DataflowStateDescriptor(
        path=path,
        type=type_name,
        source=source,
        availability=availability,
        confidence=confidence,
        producers=list(producers or []),
        sample_value=sample_value,
        protected=protected,
    )


def _merge_descriptor(
    a: DataflowStateDescriptor | None, b: DataflowStateDescriptor
) -> DataflowStateDescriptor:
    if a is None:
        return copy.deepcopy(b)
    out = copy.deepcopy(a)
    types = _split_type_union(out.type) | _split_type_union(b.type)
    if len(types) > 1:
        types.discard("any")
    out.type = "|".join(sorted(types)) if types else "any"
    sources = set(_as_list(out.source)) | set(_as_list(b.source))
    out.source = sorted(sources)[0] if len(sources) == 1 else sorted(sources)
    producers = set(out.producers) | set(b.producers)
    out.producers = sorted(x for x in producers if x)
    if out.availability != b.availability:
        out.availability = "maybe" if "maybe" in {out.availability, b.availability} else "observed"
    if out.sample_value is None and b.sample_value is not None:
        out.sample_value = b.sample_value
    out.protected = out.protected or b.protected
    return out


def _dedupe_descriptors(
    descriptors: list[DataflowStateDescriptor],
) -> list[DataflowStateDescriptor]:
    by_path: dict[str, DataflowStateDescriptor] = {}
    for desc in descriptors:
        path = desc.path
        if not path:
            continue
        existing = by_path.get(path)
        by_path[path] = _merge_descriptor(existing, desc) if existing else desc
    return [by_path[path] for path in sorted(by_path)]


def _summarize_state_map(
    state_map: dict[str, DataflowStateDescriptor],
) -> list[DataflowStateDescriptor]:
    def sort_key(item: tuple[str, DataflowStateDescriptor]) -> tuple[int, str]:
        path, desc = item
        if _is_system_descriptor(desc):
            return (2, path)
        if desc.producers:
            return (0, path)
        return (1, path)

    return [
        copy.deepcopy(desc)
        for _path, desc in sorted(state_map.items(), key=sort_key)[:MAX_STATE_FIELDS_PER_NODE]
    ]


def _canvas_summary(
    info: DataflowNodeInfo,
    *,
    is_entry: bool,
    seed: dict[str, DataflowStateDescriptor],
    variables: Mapping[str, FlowVariableConfig],
    triggers: Mapping[str, TriggerConfig],
    ui_contract_fields: tuple[FlowUIContractField, ...] = (),
) -> DataflowCanvasSummary:
    required_by_target = {req.name: req for req in info.required_inputs}
    mapped_targets = {row.target for row in info.input_mapping if row.target}
    incoming_by_path = {desc.path: desc for desc in info.incoming_state if desc.path}
    inputs: list[DataflowCanvasChip] = []
    seen_labels: set[str] = set()

    def add_chip(chip: DataflowCanvasChip) -> None:
        if chip.label in seen_labels:
            return
        seen_labels.add(chip.label)
        inputs.append(chip)

    for row in info.input_mapping:
        label = row.source_path or row.source or row.target
        req = required_by_target.get(row.target)
        add_chip(
            DataflowCanvasChip(
                label=str(label),
                target=row.target,
                status=row.status,
                type=row.type,
                required=req is not None,
                producer_node=row.producers[0] if row.producers else None,
                kind=_chip_kind_for_path(str(label)),
            )
        )
    for req in info.required_inputs:
        if req.name in mapped_targets:
            continue
        add_chip(
            DataflowCanvasChip(
                label=req.name,
                target=req.name,
                status="ok" if req.satisfied else "missing",
                type=req.type,
                required=True,
                kind=_chip_kind_for_path(req.name),
            )
        )
    for read in info.reads:
        label = read.source_path
        if not label:
            continue
        producer_node: str | None = None
        if read.source_kind == "state":
            incoming_desc = incoming_by_path.get(label)
            if incoming_desc and incoming_desc.producers:
                producer_node = incoming_desc.producers[0]
        add_chip(
            DataflowCanvasChip(
                label=str(label),
                target=read.config_path,
                status=read.status,
                type=read.type,
                producer_node=producer_node,
                kind=_chip_kind_for_path(str(label)),
            )
        )
    if is_entry:
        for chip in _build_entry_canvas_inputs(
            seed, variables, triggers, ui_contract_fields
        ):
            add_chip(chip)
    outputs: list[DataflowCanvasOutputChip] = [
        DataflowCanvasOutputChip(label=desc.path, type=desc.type) for desc in info.writes
    ]
    error_count = sum(1 for issue in info.issues if issue.severity == "error")
    warning_count = sum(1 for issue in info.issues if issue.severity == "warning")
    return DataflowCanvasSummary(
        inputs=inputs,
        outputs=outputs,
        has_issues=bool(error_count or warning_count),
        error_count=error_count,
        warning_count=warning_count,
    )


def _graph_issues(entry: str | None, nodes: dict[str, JsonObject]) -> list[DataflowIssue]:
    issues: list[DataflowIssue] = []
    if entry is None and nodes:
        issues.append(_issue("missing_entry", "warning", "Branch has nodes but no entry node."))
    elif entry is not None and entry not in nodes:
        issues.append(
            _issue("entry_not_found", "error", f"Entry node '{entry}' does not exist.", path=entry)
        )
    return issues


def _issue(
    code: str,
    severity: DataflowSeverity,
    message: str,
    *,
    path: str | None = None,
    target: str | None = None,
) -> DataflowIssue:
    return DataflowIssue(
        code=code,
        severity=severity,
        message=message,
        path=path,
        target=target,
    )


def _state_signature(
    state_map: dict[str, DataflowStateDescriptor],
) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    rows: list[tuple[str, str, tuple[str, ...], str]] = []
    for path, desc in sorted(state_map.items()):
        rows.append(
            (
                path,
                desc.type,
                tuple(desc.producers),
                desc.availability,
            )
        )
    return tuple(rows)


def _type_of_value(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _split_type_union(value: str) -> set[str]:
    raw = str(value or "any")
    return {part for part in raw.split("|") if part}


def _type_of_literal(value: str) -> str:
    v = value.strip()
    if v in {"true", "false"}:
        return "boolean"
    if v in {"null", "None"}:
        return "null"
    try:
        _ = int(v)
        return "integer"
    except ValueError:
        pass
    try:
        _ = float(v)
        return "number"
    except ValueError:
        return "string"


def _sample_value(value: JsonValue) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 120 else value[:117] + "..."
    if isinstance(value, list):
        return f"array[{len(value)}]"
    value_obj = require_json_object(value, "sample")
    keys = list(value_obj.keys())[:4]
    suffix = "..." if len(value_obj) > 4 else ""
    return "{" + ", ".join(str(k) for k in keys) + suffix + "}"


def _as_list(value: DataflowSource) -> list[str]:
    if isinstance(value, list):
        return value
    return [value]


def _top_path(path: str) -> str:
    return path.split(".", 1)[0]

"""Static data-flow inspector for the flows editor.

The inspector is intentionally conservative: it never executes user code or
remote calls, it only reads node configuration and known runtime contracts.
"""

from __future__ import annotations

import ast
import copy
import re
from collections import defaultdict, deque
from typing import Any

from core.state.mutation_policy import FROZEN_STATE_FIELDS


SYSTEM_STATE_FIELDS: dict[str, str] = {
    "content": "string|null",
    "response": "string|null",
    "result": "any",
    "validation": "object|null",
    "variables": "object",
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
MAX_CANVAS_CHIPS = 3


def inspect_flow_dataflow(
    *,
    flow_id: str | None,
    branch_id: str,
    entry: str | None,
    nodes: dict[str, Any],
    edges: list[Any],
    variables: dict[str, Any] | None = None,
    sample_state: dict[str, Any] | None = None,
    observed_runs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_nodes = _normalize_nodes(nodes)
    normalized_edges = _normalize_edges(edges)
    normalized_branch_id = branch_id or "default"
    normalized_entry = entry if isinstance(entry, str) and entry else _infer_entry(normalized_nodes, normalized_edges)

    seed = _initial_state_map(variables or {}, sample_state or {})
    incoming_by_node = _incoming_edges(normalized_edges)
    outgoing_by_node = _outgoing_edges(normalized_edges)
    reachable = _reachable_nodes(normalized_entry, outgoing_by_node)

    in_states: dict[str, dict[str, dict[str, Any]]] = {}
    out_states: dict[str, dict[str, dict[str, Any]]] = {}
    node_infos: dict[str, dict[str, Any]] = {}

    for _ in range(max(1, min(64, len(normalized_nodes) * 8 + 8))):
        changed = False
        for node_id, node in normalized_nodes.items():
            incoming_maps = []
            if node_id == normalized_entry:
                incoming_maps.append(seed)

            for edge in incoming_by_node.get(node_id, []):
                pred_state = out_states.get(edge["from_node"])
                if pred_state is None:
                    continue
                incoming_maps.append(_state_for_edge(pred_state, edge))

            if incoming_maps:
                incoming = _merge_state_maps(incoming_maps)
            else:
                incoming = copy.deepcopy(seed)

            observation = (observed_runs or {}).get(node_id) if isinstance(observed_runs, dict) else None
            info, output_state = _inspect_node(node_id, node, incoming, observation)
            if normalized_entry and node_id not in reachable and node_id != normalized_entry:
                info["issues"].append(_issue(
                    "unreachable_node",
                    "info",
                    "Node is not reachable from the branch entry.",
                ))

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
        info["incoming_state"] = _summarize_state_map(in_states.get(node_id, seed))
        info["output_state"] = _summarize_state_map(out_states.get(node_id, in_states.get(node_id, seed)))
        info["canvas"] = _canvas_summary(info)

    return {
        "flow_id": flow_id,
        "branch_id": normalized_branch_id,
        "entry": normalized_entry,
        "nodes": node_infos,
        "variables": _summarize_state_map(_variable_state_map(variables or {})),
        "issues": _graph_issues(normalized_entry, normalized_nodes),
    }


def _normalize_nodes(nodes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(nodes, dict):
        return out
    for node_id, raw in nodes.items():
        if not isinstance(node_id, str) or not node_id:
            continue
        if not isinstance(raw, dict):
            continue
        node = copy.deepcopy(raw)
        node.setdefault("node_id", node_id)
        out[node_id] = node
    return out


def _normalize_edges(edges: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(edges, list):
        return out
    for raw in edges:
        edge = _edge_to_dict(raw)
        if edge is not None:
            out.append(edge)
    return out


def _edge_to_dict(raw: Any) -> dict[str, Any] | None:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json", by_alias=True)
    if not isinstance(raw, dict):
        return None
    from_node = raw.get("from_node") or raw.get("from")
    to_node = raw.get("to_node") or raw.get("to")
    if not isinstance(from_node, str) or not from_node:
        return None
    if to_node is not None and not isinstance(to_node, str):
        return None
    return {
        "from_node": from_node,
        "to_node": to_node,
        "condition": raw.get("condition"),
        "contributes_to_join": raw.get("contributes_to_join", True) is not False,
    }


def _infer_entry(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> str | None:
    if not nodes:
        return None
    targets = {edge["to_node"] for edge in edges if edge.get("to_node")}
    for node_id in nodes:
        if node_id not in targets:
            return node_id
    return next(iter(nodes))


def _incoming_edges(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        to_node = edge.get("to_node")
        if isinstance(to_node, str) and to_node:
            out[to_node].append(edge)
    return out


def _outgoing_edges(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        out[edge["from_node"]].append(edge)
    return out


def _reachable_nodes(entry: str | None, outgoing_by_node: dict[str, list[dict[str, Any]]]) -> set[str]:
    if not entry:
        return set()
    seen = {entry}
    q: deque[str] = deque([entry])
    while q:
        node_id = q.popleft()
        for edge in outgoing_by_node.get(node_id, []):
            to_node = edge.get("to_node")
            if not isinstance(to_node, str) or not to_node or to_node in seen:
                continue
            seen.add(to_node)
            q.append(to_node)
    return seen


def _initial_state_map(variables: dict[str, Any], sample_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
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
    if isinstance(sample_state, dict):
        for path, value in _flatten_value(sample_state).items():
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


def _variable_state_map(variables: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(variables, dict):
        return out
    for key, raw in variables.items():
        if not isinstance(key, str) or not key:
            continue
        value = raw
        secret = False
        if isinstance(raw, dict) and "value" in raw:
            value = raw.get("value")
            secret = raw.get("secret") is True
        elif hasattr(raw, "value"):
            value = getattr(raw, "value")
            secret = bool(getattr(raw, "secret", False))
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


def _state_for_edge(state_map: dict[str, dict[str, Any]], edge: dict[str, Any]) -> dict[str, dict[str, Any]]:
    conditioned = edge.get("condition") not in (None, "", {})
    contributes = edge.get("contributes_to_join") is not False
    if not conditioned and contributes:
        return copy.deepcopy(state_map)
    out = copy.deepcopy(state_map)
    for desc in out.values():
        if conditioned and desc.get("availability") == "guaranteed":
            desc["availability"] = "maybe"
        if not contributes:
            desc["join_contribution"] = "non_join"
    return out


def _merge_state_maps(maps: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    if not maps:
        return {}
    total = len(maps)
    all_paths = sorted({path for m in maps for path in m})
    out: dict[str, dict[str, Any]] = {}
    for path in all_paths:
        present = [m[path] for m in maps if path in m]
        merged: dict[str, Any] | None = None
        for desc in present:
            merged = _merge_descriptor(merged, desc) if merged else copy.deepcopy(desc)
        if merged is None:
            continue
        if len(present) < total and merged.get("availability") == "guaranteed":
            merged["availability"] = "maybe"
        out[path] = merged
    return out


def _inspect_node(
    node_id: str,
    node: dict[str, Any],
    incoming: dict[str, dict[str, Any]],
    observation: Any = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    input_rows = _inspect_input_mapping(node, incoming, issues)
    reads = _inspect_config_reads(node, incoming, issues)
    writes = _infer_node_writes(node_id, node, issues)
    observed_writes = _observed_writes(node_id, observation)
    writes = _dedupe_descriptors([*writes, *observed_writes])
    output = copy.deepcopy(incoming)
    for desc in writes:
        path = desc["path"]
        existing = output.get(path)
        output[path] = _merge_descriptor(existing, desc) if existing else copy.deepcopy(desc)
    info = {
        "node_id": node_id,
        "node_type": str(node.get("type") or ""),
        "input_mapping": input_rows,
        "reads": reads,
        "writes": writes,
        "observed_writes": observed_writes,
        "observed_at": observation.get("observed_at") if isinstance(observation, dict) else None,
        "result_keys": _infer_result_keys(node, observation),
        "issues": issues,
        "incoming_state": [],
        "output_state": [],
        "canvas": {"inputs": [], "outputs": [], "has_issues": False},
    }
    return info, output


def _infer_result_keys(node: dict[str, Any], observation: Any = None) -> list[str]:
    keys: set[str] = set()
    keys.update(_schema_properties(node.get("output_schema")).keys())
    keys.update(_infer_code_return_keys(node))
    output_mapping = node.get("output_mapping")
    if isinstance(output_mapping, dict):
        keys.update(str(key) for key in output_mapping if isinstance(key, str) and key)
    state_mapping = node.get("state_mapping")
    if isinstance(state_mapping, dict):
        keys.update(str(key) for key in state_mapping if isinstance(key, str) and key)
    if isinstance(observation, dict):
        output_state = observation.get("output_state")
        if isinstance(output_state, dict):
            result = output_state.get("result")
            if isinstance(result, dict):
                keys.update(str(key) for key in result if isinstance(key, str) and key)
            api_response = output_state.get("api_response")
            if isinstance(api_response, dict):
                keys.update(str(key) for key in api_response if isinstance(key, str) and key)
    node_type = str(node.get("type") or "")
    if node_type in {"llm_node", "flow", "remote_flow", "hitl_node"}:
        keys.add("response")
    if node_type in {"code", "external_api", "mcp", "channel", "flow", "remote_flow"}:
        keys.add("result")
    return sorted(keys)


def _inspect_input_mapping(
    node: dict[str, Any],
    incoming: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping = node.get("input_mapping")
    if not isinstance(mapping, dict):
        return []
    rows: list[dict[str, Any]] = []
    for target, raw_source in mapping.items():
        if not isinstance(target, str) or not target:
            continue
        source = "" if raw_source is None else str(raw_source)
        parsed = _parse_mapping_source(source)
        row = {
            "target": target,
            "source": source,
            "source_kind": parsed["kind"],
            "source_path": parsed.get("path"),
            "status": "ok",
            "type": "any",
            "producers": [],
            "sample_value": None,
        }
        if parsed["kind"] == "state":
            path = str(parsed["path"])
            desc = incoming.get(path)
            if desc is None:
                row["status"] = "missing"
                issues.append(_issue(
                    "missing_state_path",
                    "warning",
                    f"Input mapping reads @state:{path}, but that field is not produced before this node.",
                    path=path,
                    target=target,
                ))
            else:
                row["type"] = desc.get("type", "any")
                row["producers"] = desc.get("producers", [])
                row["sample_value"] = desc.get("sample_value")
        elif parsed["kind"] == "var":
            path = f"variables.{parsed['path']}"
            desc = incoming.get(path)
            if desc is None:
                row["status"] = "missing"
                issues.append(_issue(
                    "missing_variable",
                    "warning",
                    f"Input mapping reads @var:{parsed['path']}, but this variable is not declared in the branch.",
                    path=str(parsed["path"]),
                    target=target,
                ))
            else:
                row["type"] = desc.get("type", "any")
                row["sample_value"] = desc.get("sample_value")
        else:
            row["type"] = _type_of_literal(source)
            row["sample_value"] = _sample_value(source)
        rows.append(row)
    return rows


def _inspect_config_reads(
    node: dict[str, Any],
    incoming: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, str]] = []
    for field in ("url", "body_template", "headers", "channel_config"):
        if field in node:
            refs.extend(_find_mapping_refs(node[field], field))
    reads: list[dict[str, Any]] = []
    for ref in refs:
        kind = ref["kind"]
        path = ref["path"]
        lookup = path if kind == "state" else f"variables.{path}"
        desc = incoming.get(lookup)
        status = "ok" if desc else "missing"
        reads.append({
            "source_kind": kind,
            "source_path": path,
            "config_path": ref["config_path"],
            "status": status,
            "type": desc.get("type", "any") if desc else "any",
        })
        if status == "missing":
            issues.append(_issue(
                f"missing_{kind}_path",
                "warning",
                f"Config field {ref['config_path']} reads @{kind}:{path}, but it is not available before this node.",
                path=path,
            ))
    return reads


def _infer_node_writes(
    node_id: str,
    node: dict[str, Any],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    node_type = str(node.get("type") or "")
    writes: list[dict[str, Any]] = []

    def add(path: str, type_name: str = "any", source: str = "runtime", confidence: str = "runtime_contract") -> None:
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
    output_mapping = node.get("output_mapping") if isinstance(node.get("output_mapping"), dict) else {}
    schema_props = _schema_properties(node.get("output_schema"))
    return_keys = _infer_code_return_keys(node)
    if output_mapping:
        for result_key, state_field in output_mapping.items():
            if isinstance(result_key, str) and isinstance(state_field, str):
                add(
                    state_field,
                    type_name=_schema_type(schema_props.get(result_key)),
                    source=f"output_mapping.{result_key}",
                    confidence="declared",
                )
    elif schema_props:
        for result_key, prop_schema in schema_props.items():
            add(result_key, type_name=_schema_type(prop_schema), source="output_schema", confidence="declared")

    if node_type == "llm_node":
        add("response", "string", source="llm.response")
        if bool(node.get("structured_output")) and schema_props:
            for key, prop_schema in schema_props.items():
                if not output_mapping:
                    add(key, type_name=_schema_type(prop_schema), source="structured_output", confidence="declared")
        tools = node.get("tools")
        if isinstance(tools, list) and tools:
            add("tool_results", "object", source="llm.tools")
            writes.extend(_infer_llm_tool_writes(node_id, tools, issues))
            issues.append(_issue(
                "llm_tools_dynamic_state",
                "info",
                "LLM tools can mutate state dynamically; inspect individual tools for exact fields.",
            ))
    elif node_type == "code":
        direct_fields = _infer_code_state_writes(node)
        for field in direct_fields:
            add(field, source="code.state_assignment", confidence="inferred_code")
        if output_mapping:
            pass
        elif return_keys:
            for key in return_keys:
                add(key, source="code.return", confidence="inferred_code")
        else:
            add("result", source="code.return", confidence="dynamic")
            issues.append(_issue(
                "code_return_dynamic",
                "info",
                "Code return shape is dynamic or could not be inferred statically.",
            ))
    elif node_type == "external_api":
        state_mapping = node.get("state_mapping") if isinstance(node.get("state_mapping"), dict) else {}
        for response_field, state_field in state_mapping.items():
            if isinstance(response_field, str) and isinstance(state_field, str):
                add(state_field, source=f"state_mapping.{response_field}", confidence="declared")
        add("api_response", "any", source="external_api.response")
        add("api_status", "string", source="external_api.status")
        add("result", "any", source="external_api.response")
        if not output_mapping:
            issues.append(_issue(
                "external_api_response_dynamic",
                "info",
                "External API data may be a JSON object; without output_mapping its keys can be copied to state by BaseNode.",
            ))
    elif node_type == "mcp":
        state_mapping = node.get("state_mapping") if isinstance(node.get("state_mapping"), dict) else {}
        for _response_field, state_field in state_mapping.items():
            if isinstance(state_field, str):
                add(state_field, "string", source="state_mapping", confidence="declared")
        add("mcp_result", "string", source="mcp.result")
        add("result", "string", source="mcp.result")
    elif node_type == "channel":
        add("channel_result", "any", source="channel.result")
        add("result", "any", source="channel.result")
        if not output_mapping:
            issues.append(_issue(
                "channel_result_dynamic",
                "info",
                "Channel handlers can return objects; without output_mapping their keys may be copied to state by BaseNode.",
            ))
    elif node_type == "flow":
        add("response", "string|null", source="nested_flow.response")
        add("result", "any", source="nested_flow.result")
        nested = node.get("__dataflow_nested")
        if isinstance(nested, dict) and isinstance(nested.get("nodes"), dict):
            nested_writes = _nested_flow_writes(node_id, node, nested)
            writes.extend(nested_writes)
            if nested_writes:
                issues.append(_issue(
                    "nested_flow_static_expanded",
                    "info",
                    "Nested flow state writes are expanded from the referenced graph.",
                ))
        else:
            issues.append(_issue(
                "nested_flow_state_dynamic",
                "info",
                "Nested flow copies its returned state back to the parent; exact fields depend on the nested graph.",
            ))
    elif node_type == "remote_flow":
        add("response", "string|null", source="remote_flow.response")
        add("remote_status", "string", source="remote_flow.status")
        add("result", "any", source="remote_flow.response")
    elif node_type == "hitl_node":
        add("response", "string|null", source="hitl.resume")
        issues.append(_issue(
            "hitl_interrupt",
            "info",
            "Initial HITL execution interrupts the graph; response is written after operator resume.",
        ))
    elif node_type == "resource":
        pass
    elif output_mapping or schema_props:
        pass
    else:
        add("result", "any", source="node.result", confidence="dynamic")

    return _dedupe_descriptors(writes)


def _observed_writes(node_id: str, observation: Any) -> list[dict[str, Any]]:
    if not isinstance(observation, dict):
        return []
    diff = observation.get("diff")
    if not isinstance(diff, list):
        return []
    writes: list[dict[str, Any]] = []
    for item in diff:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        if item.get("change_type") == "removed":
            value = None
        else:
            value = item.get("new_value")
        writes.append(_descriptor(
            path,
            type_name=_type_of_value(value),
            source="observed_run",
            availability="observed",
            confidence="observed",
            producers=[node_id],
            sample_value=_sample_value(value),
            protected=_top_path(path) in FROZEN_STATE_FIELDS,
        ))
    return _dedupe_descriptors(writes)


def _infer_llm_tool_writes(
    node_id: str,
    tools: list[Any],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    for idx, raw_tool in enumerate(tools):
        if hasattr(raw_tool, "model_dump"):
            raw_tool = raw_tool.model_dump(mode="json")
        if isinstance(raw_tool, str):
            tool_name = raw_tool
            writes.append(_descriptor(
                f"tool_results.{tool_name}",
                type_name="any",
                source="llm.tool_result",
                availability="maybe",
                confidence="runtime_contract",
                producers=[node_id],
            ))
            continue
        if not isinstance(raw_tool, dict):
            continue
        tool_name = _tool_display_id(raw_tool, idx)
        writes.append(_descriptor(
            f"tool_results.{tool_name}",
            type_name="any",
            source="llm.tool_result",
            availability="maybe",
            confidence="runtime_contract",
            producers=[node_id],
        ))
        if isinstance(raw_tool.get("code"), str) and raw_tool["code"].strip():
            for path in sorted(_infer_code_state_writes(raw_tool)):
                writes.append(_descriptor(
                    path,
                    type_name="any",
                    source=f"tool.{tool_name}.state_assignment",
                    availability="maybe",
                    confidence="inferred_code",
                    producers=[node_id],
                    protected=_top_path(path) in FROZEN_STATE_FIELDS,
                ))
                _append_write_issues(path, f"tool.{tool_name}.state_assignment", issues)
        tool_type = str(raw_tool.get("type") or "")
        if tool_type in {"flow", "llm_node"} and not raw_tool.get("code"):
            issues.append(_issue(
                "llm_tool_dynamic_state",
                "info",
                f"Tool '{tool_name}' can mutate state depending on runtime execution.",
            ))
    return _dedupe_descriptors(writes)


def _nested_flow_writes(node_id: str, node: dict[str, Any], nested: dict[str, Any]) -> list[dict[str, Any]]:
    flow_id = str(node.get("flow_id") or "nested")
    writes: list[dict[str, Any]] = []
    for nested_info in (nested.get("nodes") or {}).values():
        if not isinstance(nested_info, dict):
            continue
        for nested_write in nested_info.get("writes") or []:
            if not isinstance(nested_write, dict):
                continue
            path = nested_write.get("path")
            if not isinstance(path, str) or not path:
                continue
            writes.append(_descriptor(
                path,
                type_name=str(nested_write.get("type") or "any"),
                source=f"nested_flow.{flow_id}",
                availability="maybe",
                confidence="nested_static",
                producers=[node_id],
                sample_value=nested_write.get("sample_value"),
                protected=_top_path(path) in FROZEN_STATE_FIELDS,
            ))
    return _dedupe_descriptors(writes)


def _tool_display_id(tool: dict[str, Any], idx: int) -> str:
    for key in ("tool_id", "name", "function", "mcp_tool_name", "tool_name"):
        value = tool.get(key)
        if isinstance(value, str) and value:
            return value
    return f"tool_{idx + 1}"


def _append_write_issues(path: str, source: str, issues: list[dict[str, Any]]) -> None:
    top = _top_path(path)
    if top in FROZEN_STATE_FIELDS:
        issues.append(_issue(
            "frozen_state_write",
            "error",
            f"{source} writes frozen state field '{path}'. Runtime may reject or make this field unsafe to rely on.",
            path=path,
        ))
    if "." in path and source.startswith(("output_mapping", "state_mapping")):
        issues.append(_issue(
            "nested_mapping_path_runtime",
            "warning",
            f"{source} targets '{path}'. Runtime writes mapping targets as a top-level state attribute, not as a nested path.",
            path=path,
        ))


def _infer_code_state_writes(node: dict[str, Any]) -> set[str]:
    code = node.get("code")
    if not isinstance(code, str) or not code.strip():
        return set()
    language = str(node.get("language") or "python").lower()
    if language == "python":
        return _infer_python_state_writes(code)
    return _infer_text_state_writes(code)


def _infer_code_return_keys(node: dict[str, Any]) -> set[str]:
    code = node.get("code")
    if not isinstance(code, str) or not code.strip():
        return set()
    language = str(node.get("language") or "python").lower()
    if language == "python":
        return _infer_python_return_keys(code)
    return _infer_text_return_keys(code)


def _infer_python_state_writes(code: str) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _infer_text_state_writes(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                targets = [node.target]
            for target in targets:
                path = _python_state_target_path(target)
                if path:
                    out.add(path)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "update" and _python_is_state_expr(node.func.value):
                if node.args and isinstance(node.args[0], ast.Dict):
                    for key_node in node.args[0].keys:
                        key = _literal_string(key_node)
                        if key:
                            out.add(key)
    return out


def _infer_python_return_keys(code: str) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _infer_text_return_keys(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key_node in node.value.keys:
                key = _literal_string(key_node)
                if key:
                    out.add(key)
    return out


def _python_state_target_path(target: ast.AST) -> str | None:
    if isinstance(target, ast.Attribute) and _python_is_state_expr(target.value):
        return target.attr
    if isinstance(target, ast.Subscript) and _python_is_state_expr(target.value):
        return _literal_string(target.slice)
    return None


def _python_is_state_expr(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "state"


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return node.value
    if isinstance(node, ast.Str) and node.s:
        return node.s
    return None


def _infer_text_state_writes(code: str) -> set[str]:
    out = set(re.findall(r"\bstate\.([A-Za-z_][A-Za-z0-9_]*)\s*=", code))
    out.update(re.findall(r"\bstate\[['\"]([A-Za-z_][A-Za-z0-9_.-]*)['\"]\]\s*=", code))
    return out


def _infer_text_return_keys(code: str) -> set[str]:
    returns = re.findall(r"\breturn\s+\{(?P<body>[^}]{0,4000})\}", code, flags=re.MULTILINE | re.DOTALL)
    out: set[str] = set()
    for body in returns:
        out.update(re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_.-]*)['\"]\s*:", body))
        out.update(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:", body))
    return out


def _schema_properties(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    if isinstance(props, dict):
        return props
    return {}


def _schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "any"
    type_value = schema.get("type")
    if isinstance(type_value, list):
        return "|".join(str(item) for item in type_value)
    if isinstance(type_value, str) and type_value:
        return type_value
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return "any"


def _parse_mapping_source(source: str) -> dict[str, Any]:
    if source.startswith("@state:"):
        return {"kind": "state", "path": source[len("@state:"):]}
    if source.startswith("@var:"):
        return {"kind": "var", "path": source[len("@var:"):]}
    return {"kind": "const", "path": None}


def _find_mapping_refs(value: Any, config_path: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if isinstance(value, str):
        for kind, path in re.findall(r"@(state|var):([A-Za-z0-9_.\-\[\]]+)", value):
            refs.append({"kind": kind, "path": path, "config_path": config_path})
    elif isinstance(value, dict):
        for key, item in value.items():
            refs.extend(_find_mapping_refs(item, f"{config_path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            refs.extend(_find_mapping_refs(item, f"{config_path}[{idx}]"))
    return refs


def _flatten_value(value: Any, prefix: str = "", depth: int = 0) -> dict[str, Any]:
    if depth > 3:
        return {prefix: value} if prefix else {}
    out: dict[str, Any] = {}
    if prefix:
        out[prefix] = value
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                continue
            child = f"{prefix}.{key}" if prefix else key
            out.update(_flatten_value(item, child, depth + 1))
    return out


def _descriptor(
    path: str,
    *,
    type_name: str,
    source: str,
    availability: str,
    confidence: str,
    producers: list[str] | None = None,
    sample_value: Any = None,
    protected: bool = False,
) -> dict[str, Any]:
    return {
        "path": path,
        "type": type_name,
        "source": source,
        "availability": availability,
        "confidence": confidence,
        "producers": list(producers or []),
        "sample_value": sample_value,
        "protected": protected,
    }


def _merge_descriptor(a: dict[str, Any] | None, b: dict[str, Any]) -> dict[str, Any]:
    if a is None:
        return copy.deepcopy(b)
    out = copy.deepcopy(a)
    types = _split_type_union(out.get("type")) | _split_type_union(b.get("type"))
    if len(types) > 1:
        types.discard("any")
    out["type"] = "|".join(sorted(types)) if types else "any"
    sources = set(_as_list(out.get("source"))) | set(_as_list(b.get("source")))
    out["source"] = sorted(sources)[0] if len(sources) == 1 else sorted(sources)
    producers = set(_as_list(out.get("producers"))) | set(_as_list(b.get("producers")))
    out["producers"] = sorted(x for x in producers if x)
    if out.get("availability") != b.get("availability"):
        out["availability"] = "maybe" if "maybe" in {out.get("availability"), b.get("availability")} else "observed"
    if out.get("sample_value") is None and b.get("sample_value") is not None:
        out["sample_value"] = b.get("sample_value")
    out["protected"] = bool(out.get("protected") or b.get("protected"))
    return out


def _dedupe_descriptors(descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for desc in descriptors:
        path = desc.get("path")
        if not isinstance(path, str) or not path:
            continue
        existing = by_path.get(path)
        by_path[path] = _merge_descriptor(existing, desc) if existing else desc
    return [by_path[path] for path in sorted(by_path)]


def _summarize_state_map(state_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
        path, desc = item
        if desc.get("source") == "system":
            return (2, path)
        if desc.get("producers"):
            return (0, path)
        return (1, path)

    return [copy.deepcopy(desc) for _path, desc in sorted(state_map.items(), key=sort_key)[:MAX_STATE_FIELDS_PER_NODE]]


def _canvas_summary(info: dict[str, Any]) -> dict[str, Any]:
    input_rows = list(info.get("input_mapping") or [])
    inputs = []
    for row in input_rows:
        label = row.get("source_path") or row.get("source") or row.get("target")
        inputs.append({
            "label": str(label),
            "target": row.get("target"),
            "status": row.get("status"),
            "type": row.get("type"),
        })
    for read in info.get("reads") or []:
        label = read.get("source_path")
        if not label:
            continue
        inputs.append({
            "label": str(label),
            "target": read.get("config_path"),
            "status": read.get("status"),
            "type": read.get("type"),
        })
    if not inputs:
        for desc in info.get("incoming_state") or []:
            if desc.get("source") == "system":
                continue
            inputs.append({
                "label": desc.get("path"),
                "target": None,
                "status": "ok",
                "type": desc.get("type"),
            })
            if len(inputs) >= MAX_CANVAS_CHIPS:
                break
    outputs = [
        {
            "label": desc.get("path"),
            "type": desc.get("type"),
            "status": "ok",
        }
        for desc in (info.get("writes") or [])[:MAX_CANVAS_CHIPS]
    ]
    return {
        "inputs": inputs[:MAX_CANVAS_CHIPS],
        "outputs": outputs[:MAX_CANVAS_CHIPS],
        "has_issues": any(issue.get("severity") in {"warning", "error"} for issue in info.get("issues", [])),
    }


def _graph_issues(entry: str | None, nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if entry is None and nodes:
        issues.append(_issue("missing_entry", "warning", "Branch has nodes but no entry node."))
    elif entry is not None and entry not in nodes:
        issues.append(_issue("entry_not_found", "error", f"Entry node '{entry}' does not exist.", path=entry))
    return issues


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    path: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    out = {"code": code, "severity": severity, "message": message}
    if path is not None:
        out["path"] = path
    if target is not None:
        out["target"] = target
    return out


def _state_signature(state_map: dict[str, dict[str, Any]]) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    rows = []
    for path, desc in sorted(state_map.items()):
        rows.append((
            path,
            str(desc.get("type") or ""),
            tuple(str(p) for p in desc.get("producers") or []),
            str(desc.get("availability") or ""),
        ))
    return tuple(rows)


def _type_of_value(value: Any) -> str:
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


def _split_type_union(value: Any) -> set[str]:
    raw = str(value or "any")
    return {part for part in raw.split("|") if part}


def _type_of_literal(value: str) -> str:
    v = value.strip()
    if v in {"true", "false"}:
        return "boolean"
    if v in {"null", "None"}:
        return "null"
    try:
        int(v)
        return "integer"
    except ValueError:
        pass
    try:
        float(v)
        return "number"
    except ValueError:
        return "string"


def _sample_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 120 else value[:117] + "..."
    if isinstance(value, list):
        return f"array[{len(value)}]"
    if isinstance(value, dict):
        keys = list(value.keys())[:4]
        suffix = "..." if len(value) > 4 else ""
        return "{" + ", ".join(str(k) for k in keys) + suffix + "}"
    return str(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _top_path(path: str) -> str:
    return path.split(".", 1)[0]

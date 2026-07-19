"""Diff между двумя ExecutionState-снимками для canvas preview и execute API."""

from __future__ import annotations

from pydantic import BaseModel

from core.types import JsonObject, JsonValue, require_json_object

STATE_DIFF_SKIP_KEYS: frozenset[str] = frozenset({
    "task_id",
    "context_id",
    "user_id",
    "initiator_user_id",
    "session_id",
    "messages",
    "prompt_history",
    "node_history",
    "nested_states",
    "current_nodes",
    "branch_id",
    "flow_config_version",
    "user_groups",
    "interrupt_path",
    "tool_results",
    "triggers",
    "files",
    "breakpoints",
    "scheduled_tasks",
    "reasoning_history",
    "reflection_history",
    "pending_reasoning",
    "breakpoint_hit",
    "breakpoint_state",
    "interrupt",
    "join_arrived_preds",
    "hitl_handoff_correlation_id",
    "hitl_streamed_closing_text",
    "flow_deadline_monotonic",
    "flow_timeout_effective_seconds",
    "terminal_task_state",
    "terminal_task_error",
    "llm_context_memory_cursor",
    "handoff_depth",
    "handoff_trace_id",
    "handoff_parent_session_id",
    "handback_return_variables",
    "agent_plan",
})

CANVAS_DIFF_LIMIT = 8
CANVAS_PREVIEW_MAX_LEN = 200

_PRIMARY_FIELD_CANDIDATES: tuple[str, ...] = (
    "response",
    "result",
    "mcp_result",
    "api_response",
    "channel_result",
    "validation",
)


class DiffItem(BaseModel):
    """Элемент diff между state-снимками."""

    path: str
    old_value: JsonValue
    new_value: JsonValue
    change_type: str


def compute_state_diff(
    old: JsonObject,
    new: JsonObject,
    path: str = "",
) -> list[DiffItem]:
    """Вычисляет diff между двумя state JSON-объектами."""
    diff_items: list[DiffItem] = []
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        if key in STATE_DIFF_SKIP_KEYS:
            continue

        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            diff_items.append(
                DiffItem(path=current_path, old_value=None, new_value=new_val, change_type="added")
            )
        elif key not in new:
            diff_items.append(
                DiffItem(
                    path=current_path, old_value=old_val, new_value=None, change_type="removed"
                )
            )
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            diff_items.extend(
                compute_state_diff(
                    require_json_object(old_val, f"diff.old.{current_path}"),
                    require_json_object(new_val, f"diff.new.{current_path}"),
                    current_path,
                )
            )
        elif old_val != new_val:
            diff_items.append(
                DiffItem(
                    path=current_path, old_value=old_val, new_value=new_val, change_type="changed"
                )
            )

    return diff_items


def top_state_diff_items(items: list[DiffItem], limit: int = CANVAS_DIFF_LIMIT) -> list[DiffItem]:
    """Возвращает первые limit diff-элементов для canvas preview."""
    if limit <= 0:
        raise ValueError("top_state_diff_items: limit must be positive")
    return items[:limit]


def infer_primary_field(after: JsonObject, diff_items: list[DiffItem]) -> str:
    """Определяет главное поле результата ноды для canvas preview."""
    for field_name in _PRIMARY_FIELD_CANDIDATES:
        if field_name in after and after[field_name] is not None:
            return field_name
    if diff_items:
        first_path = diff_items[0].path
        root = first_path.split(".", 1)[0]
        if root:
            return root
    return ""


def _is_status_entry(value: JsonValue) -> bool:
    return isinstance(value, dict) and "ok" in value


def _is_status_map(value: JsonValue) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    return all(_is_status_entry(item) for item in value.values())


def _format_status_map(value: JsonObject) -> str:
    parts: list[str] = []
    for key, entry in value.items():
        if not isinstance(entry, dict):
            continue
        ok_value = entry.get("ok")
        status_text = "ok" if ok_value is True else "fail"
        part = f"{key}: {status_text}"
        latency_ms = entry.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            part = f"{part} · {int(latency_ms)} ms"
        parts.append(part)
    return ", ".join(parts)


def summarize_canvas_value(value: JsonValue, *, max_len: int = CANVAS_PREVIEW_MAX_LEN) -> str:
    """Сжимает значение state для canvas preview без полного JSON."""
    if value is None:
        return "null"
    if isinstance(value, str):
        if len(value) <= max_len:
            return value
        if max_len <= 1:
            return "…"
        return f"{value[: max_len - 1]}…"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return f"{len(value)} items"
    if _is_status_map(value):
        text = _format_status_map(require_json_object(value, "summarize_canvas_value.status_map"))
        if len(text) <= max_len:
            return text
        if max_len <= 1:
            return "…"
        return f"{text[: max_len - 1]}…"
    if isinstance(value, dict):
        return f"{len(value)} fields"
    text = str(value)
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    return f"{text[: max_len - 1]}…"


def _find_diff_value(diff_items: list[DiffItem], path_prefix: str) -> JsonValue | None:
    for item in diff_items:
        if item.path == path_prefix or item.path.startswith(f"{path_prefix}."):
            return item.new_value
    return None


def build_canvas_result_preview(
    node_type: str,
    after: JsonObject,
    diff_items: list[DiffItem],
    primary_field: str,
) -> str:
    """Строит человекочитаемый preview результата ноды для canvas."""
    response = after.get("response")
    if node_type == "llm_node" and isinstance(response, str) and response:
        return summarize_canvas_value(response)

    if node_type == "mcp":
        status_value = _find_diff_value(diff_items, "variables.search_providers_status")
        if status_value is None:
            status_value = _find_diff_value(diff_items, "search_providers_status")
        if status_value is not None and _is_status_map(status_value):
            return summarize_canvas_value(status_value)
        mcp_result = after.get("mcp_result")
        if mcp_result is not None:
            return summarize_canvas_value(mcp_result)

    if node_type == "code":
        result_value = after.get("result")
        if result_value is not None:
            return summarize_canvas_value(result_value)

    if node_type == "external_api":
        api_status = after.get("api_status")
        if api_status is not None:
            preview = f"HTTP {api_status}"
            api_response = after.get("api_response")
            if api_response is not None:
                body = summarize_canvas_value(api_response, max_len=80)
                preview = f"{preview} · {body}"
            if len(preview) <= CANVAS_PREVIEW_MAX_LEN:
                return preview
            return preview[: CANVAS_PREVIEW_MAX_LEN - 1] + "…"

    if node_type in {"flow", "remote_flow"}:
        result_value = after.get("result")
        if result_value is not None:
            return summarize_canvas_value(result_value)

    if node_type == "hitl_node":
        return "Handoff to operator"

    if node_type == "channel":
        return "Message sent"

    if isinstance(response, str) and response:
        return summarize_canvas_value(response)

    result_value = after.get("result")
    if result_value is not None:
        return summarize_canvas_value(result_value)

    if primary_field:
        primary_value = after.get(primary_field)
        if primary_value is not None:
            return summarize_canvas_value(primary_value)

    if diff_items:
        first = diff_items[0]
        label = first.path.removeprefix("variables.")
        return f"{label}: {summarize_canvas_value(first.new_value, max_len=80)}"

    return ""


def execution_state_to_diff_json(state: object) -> JsonObject:
    """Сериализует ExecutionState в JSON для diff без flow_config."""
    from core.state import ExecutionState

    if not isinstance(state, ExecutionState):
        raise TypeError("execution_state_to_diff_json: state must be ExecutionState")
    raw = state.model_dump(mode="json", exclude_none=False)
    raw.pop("flow_config", None)
    return require_json_object(raw, "ExecutionState")

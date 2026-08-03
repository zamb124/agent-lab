"""Allowlisted ExecutionState projection для isolated code runners."""

from __future__ import annotations

from core.a2a.codec import messages_to_json_list
from core.files.file_ref import FileRef
from core.state import ExecutionState
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject, require_json_object


def _file_ref_summary(file_ref: FileRef) -> JsonObject:
    return {
        "file_id": file_ref.file_id,
        "original_name": file_ref.original_name,
        "url": file_ref.url,
        "content_type": file_ref.content_type,
        "file_size": file_ref.file_size,
        "capabilities": file_ref.capabilities.model_dump(mode="json"),
    }


def build_tool_context_view(state: ExecutionState) -> JsonObject:
    """
    Строит урезанное представление ExecutionState для sandbox code runners.

    Включено: идентификаторы сессии/контекста/задачи/пользователя, branch_id,
    flow_config_version, content, variables, user_groups, current_nodes,
    messages, tool_results, ui_events_pending, краткие summaries файлов,
    result, validation, triggers, а также пользовательские extra-поля
    (`json_extra`), кроме имён из FROZEN_STATE_FIELDS.

    Исключено: node_history, reasoning_history, prompt_history, nested_states,
    child_workflows, execution_exceptions, interrupt_path, breakpoints,
    agent_plan, flow_deadline_monotonic, flow_timeout_effective_seconds
    и прочие runtime-only поля с полной историей исполнения или секретами
    платформы.
    """
    view: JsonObject = {
        "task_id": state.task_id,
        "context_id": state.context_id,
        "user_id": state.user_id,
        "session_id": state.session_id,
        "branch_id": state.branch_id,
        "current_nodes": list(state.current_nodes),
        "variables": dict(state.variables),
        "user_groups": list(state.user_groups),
        "files": [_file_ref_summary(file_ref) for file_ref in state.files],
        "messages": messages_to_json_list(state.messages),
        "tool_results": dict(state.tool_results),
        "ui_events_pending": [
            event.model_dump(mode="json") for event in state.ui_events_pending
        ],
    }
    if state.initiator_user_id is not None:
        view["initiator_user_id"] = state.initiator_user_id
    if state.flow_config_version is not None:
        view["flow_config_version"] = state.flow_config_version
    if state.content is not None:
        view["content"] = state.content
    if state.response is not None:
        view["response"] = state.response
    if state.result is not None:
        view["result"] = state.result
    if state.validation is not None:
        view["validation"] = dict(state.validation)
    if state.triggers:
        view["triggers"] = {
            trigger_id: snapshot.model_dump(mode="json")
            for trigger_id, snapshot in state.triggers.items()
        }
    for extra_key, extra_value in state.json_extra().items():
        if extra_key in FROZEN_STATE_FIELDS:
            raise ValueError(
                f"ExecutionState extra field '{extra_key}' conflicts with frozen system field"
            )
        if extra_key in view:
            raise ValueError(
                f"ExecutionState extra field '{extra_key}' conflicts with allowlisted context key"
            )
        view[extra_key] = extra_value
    return require_json_object(view, "tool_context_view")

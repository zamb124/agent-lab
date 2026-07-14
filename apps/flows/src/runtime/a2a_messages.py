"""
Единая фабрика A2A Message для flows (user / assistant / tool / system).

Все user-сообщения с привязкой к node_id создаются здесь — без дублей в interrupt_manager и llm_runner.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from a2a.types import Message, Part, Role, TextPart

from core.clients.llm import LLMToolCall
from core.types import JsonObject


def build_user_message(
    content: str,
    source_node_id: str,
    context_id: str | None = None,
    task_id: str | None = None,
) -> Message:
    """Сообщение пользователя с metadata.node_id для фильтрации и nested resume."""
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata={"node_id": source_node_id},
    )


def build_assistant_message(
    content: str,
    source_node_id: str,
    tool_calls: Sequence[LLMToolCall | JsonObject] | None = None,
    context_id: str | None = None,
    task_id: str | None = None,
    *,
    interrupted: bool = False,
) -> Message:
    meta: JsonObject = {"node_id": source_node_id}
    if tool_calls:
        meta["tool_calls"] = [
            LLMToolCall.model_validate(tool_call).model_dump(mode="json", exclude_none=True)
            for tool_call in tool_calls
        ]
    if interrupted:
        meta["interrupted"] = True
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata=meta,
    )


def build_operator_message(
    content: str,
    source_node_id: str,
    *,
    operator_user_id: str,
    message_id: str,
    context_id: str | None = None,
    task_id: str | None = None,
    file_ids: list[str] | None = None,
) -> Message:
    """Сообщение оператора в HITL: role=agent + metadata.hitl_role=operator.

    `message_id` детерминирован снаружи (идемпотентность durable append).
    `file_ids` — уже загруженные платформенные файлы (attach в composer).
    """
    resolved_file_ids = [fid for fid in (file_ids or []) if fid.strip()]
    metadata: JsonObject = {
        "node_id": source_node_id,
        "hitl_role": "operator",
        "operator_user_id": operator_user_id,
    }
    if resolved_file_ids:
        metadata["hitl_file_ids"] = resolved_file_ids
    return Message(
        message_id=message_id,
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata=metadata,
    )


def build_tool_result_message(
    tool_call_id: str,
    content: str,
    source_node_id: str,
    context_id: str | None = None,
    task_id: str | None = None,
) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata={"tool_call_id": tool_call_id, "node_id": source_node_id},
    )


def build_system_message(
    content: str,
    context_id: str | None = None,
    task_id: str | None = None,
    source_node_id: str | None = None,
) -> Message:
    meta: JsonObject = {"system": True}
    if source_node_id is not None:
        meta["node_id"] = source_node_id
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata=meta,
    )

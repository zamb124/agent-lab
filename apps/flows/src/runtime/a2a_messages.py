"""
Единая фабрика A2A Message для flows (user / assistant / tool / system).

Все user-сообщения с привязкой к node_id создаются здесь — без дублей в interrupt_manager и llm_runner.
"""

from __future__ import annotations

import uuid
from typing import Any

from a2a.types import Message, Part, Role, TextPart


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
    tool_calls: list[dict[str, Any]] | None = None,
    context_id: str | None = None,
    task_id: str | None = None,
    *,
    interrupted: bool = False,
) -> Message:
    meta: dict[str, Any] = {"node_id": source_node_id}
    if tool_calls:
        meta["tool_calls"] = tool_calls
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
    meta: dict[str, Any] = {"system": True}
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

"""A2A/OpenAI-compatible message conversion for LLM clients."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Any, Literal

from a2a.types import (
    FilePart,
    FileWithBytes,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)
from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject

MessageInput = str | list[str] | Message | list[Message] | dict[str, Any] | list[dict[str, Any]]

StreamEvent = TaskArtifactUpdateEvent | TaskStatusUpdateEvent


class LLMToolCallFunction(StrictBaseModel):
    """OpenAI-compatible function payload preserved in assistant history."""

    name: str
    arguments: str


class LLMToolCall(StrictBaseModel):
    """Canonical LLM tool call produced by providers and executed by Flow tools."""

    id: str
    name: str
    arguments: JsonObject = Field(default_factory=dict)
    type: Literal["function"] = "function"
    function: LLMToolCallFunction | None = None


def extract_content_parts(parts: list[Any]) -> tuple[list[dict[str, Any]], bool]:
    """
    Извлекает content parts из списка A2A parts.

    Returns:
        Tuple (content_parts, has_files) где:
        - content_parts: список OpenAI content parts
        - has_files: True если есть файлы (нужен multimodal формат)
    """
    content_parts: list[dict[str, Any]] = []
    has_files = False

    for part in parts:
        if hasattr(part, "root"):
            root = part.root
        elif isinstance(part, dict):
            root = part.get("root", part)
        else:
            continue

        if isinstance(root, TextPart):
            content_parts.append({"type": "text", "text": root.text})
        elif isinstance(root, dict) and "text" in root:
            content_parts.append({"type": "text", "text": root["text"]})
        elif isinstance(root, FilePart):
            has_files = True
            file_obj = root.file
            if isinstance(file_obj, FileWithBytes):
                mime_type = file_obj.mime_type or "image/png"
                b64_data = file_obj.bytes
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    }
                )
        elif isinstance(root, dict) and "file" in root:
            has_files = True
            file_obj = root["file"]
            if isinstance(file_obj, dict) and "bytes" in file_obj:
                mime_type = file_obj.get("mimeType") or file_obj.get("mime_type") or "image/png"
                b64_data = file_obj["bytes"]
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    }
                )

    return content_parts, has_files


def message_to_openai(message: Message | dict[str, Any] | str) -> dict[str, Any]:
    """
    A2A Message в формат OpenAI API.

    Поддерживает:
    - Message объекты
    - dict (после десериализации из state)
    - строки
    - Multimodal: TextPart + FilePart
    """
    role_map = {
        Role.user: "user",
        Role.agent: "assistant",
        "user": "user",
        "agent": "assistant",
    }

    if isinstance(message, str):
        if "context_id=" in message and "parts=" in message and "role=" in message:
            text_match = re.search(r"text='([^']*)'", message)
            if text_match:
                content = text_match.group(1)
            else:
                text_match = re.search(r'text="([^"]*)"', message)
                content = text_match.group(1) if text_match else message

            role_str = "user"
            if "role=<Role.agent:" in message or "role='agent'" in message:
                role_str = "assistant"

            return {"role": role_str, "content": content}

        return {"role": "user", "content": message}

    if isinstance(message, dict):
        role_raw = message.get("role", "user")
        role = role_raw if isinstance(role_raw, (Role, str)) else "user"
        metadata = message.get("metadata") or {}
        parts = message.get("parts", [])

        if "content" in message and message["content"]:
            return {
                "role": role_map.get(role, str(role)),
                "content": message["content"],
            }
    else:
        role = message.role
        metadata = message.metadata or {}
        parts = message.parts

    content_parts, has_files = extract_content_parts(parts)
    if has_files:
        content: str | list[dict[str, Any]] = content_parts
    else:
        content = "".join(
            content_part["text"]
            for content_part in content_parts
            if content_part.get("type") == "text"
        )

    is_system = metadata.get("system", False)
    openai_role = "system" if is_system else role_map.get(role, "user")
    if metadata.get("tool_call_id"):
        openai_role = "tool"

    openai_message: dict[str, Any] = {
        "role": openai_role,
        "content": content,
    }

    if metadata.get("tool_calls"):
        openai_message["tool_calls"] = metadata["tool_calls"]

    if metadata.get("tool_call_id"):
        openai_message["tool_call_id"] = metadata["tool_call_id"]

    return openai_message


def messages_to_openai(messages: Sequence[Message | dict[str, Any] | str]) -> list[dict[str, Any]]:
    """Внутренняя функция - список A2A Message в формат OpenAI API."""
    return [message_to_openai(message) for message in messages]


def normalize_messages(messages: MessageInput) -> list[Message]:
    """
    Нормализует различные форматы messages в List[Message].

    Поддерживает:
    - str: одно сообщение пользователя
    - List[str]: список сообщений (чередуются user/assistant)
    - Message: одно A2A сообщение
    - List[Message]: список A2A сообщений
    - Dict: одно сообщение в формате {"role": "user", "content": "text"}
    - List[Dict]: список сообщений в формате OpenAI
    """
    if isinstance(messages, str):
        return [
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=messages))],
            )
        ]

    if isinstance(messages, Message):
        return [messages]

    if isinstance(messages, dict):
        role, metadata = _role_and_metadata_from_openai_dict(messages)
        content = messages.get("content", "")
        if not isinstance(content, str):
            raise ValueError("message.content must be string")
        return [
            Message(
                message_id=str(uuid.uuid4()),
                role=role,
                parts=[Part(root=TextPart(text=content))],
                metadata=metadata or None,
            )
        ]

    if isinstance(messages, list):
        if not messages:
            return []

        first = messages[0]

        if isinstance(first, str):
            string_messages: list[Message] = []
            for message_index, text in enumerate(messages):
                if not isinstance(text, str):
                    raise ValueError("messages list must contain only strings")
                role = Role.user if message_index % 2 == 0 else Role.agent
                string_messages.append(
                    Message(
                        message_id=str(uuid.uuid4()),
                        role=role,
                        parts=[Part(root=TextPart(text=text))],
                    )
                )
            return string_messages

        if isinstance(first, Message):
            typed_messages: list[Message] = []
            for message in messages:
                if not isinstance(message, Message):
                    raise ValueError("messages list must contain only Message objects")
                typed_messages.append(message)
            return typed_messages

        if isinstance(first, dict):
            dict_messages: list[Message] = []
            for message in messages:
                if not isinstance(message, dict):
                    raise ValueError("messages list must contain only dict objects")
                role, metadata = _role_and_metadata_from_openai_dict(message)
                content = message.get("content", "")
                if not isinstance(content, str):
                    raise ValueError("message.content must be string")
                dict_messages.append(
                    Message(
                        message_id=str(uuid.uuid4()),
                        role=role,
                        parts=[Part(root=TextPart(text=content))],
                        metadata=metadata or None,
                    )
                )
            return dict_messages

    raise ValueError(f"Unsupported messages type: {type(messages)}")


def _role_and_metadata_from_openai_dict(message: dict[str, Any]) -> tuple[Role, dict[str, Any]]:
    role_raw = str(message.get("role", "user"))
    metadata: dict[str, Any] = {}
    if role_raw == "system":
        metadata["system"] = True
        return Role.user, metadata
    if role_raw == "tool":
        tool_call_id = message.get("tool_call_id")
        if tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        return Role.agent, metadata
    if message.get("tool_calls"):
        metadata["tool_calls"] = message["tool_calls"]
    if role_raw in ("assistant", "agent"):
        return Role.agent, metadata
    return Role.user, metadata


def messages_have_non_text_parts(openai_messages: list[dict[str, Any]]) -> bool:
    for message in openai_messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") != "text":
                return True
    return False


__all__ = [
    "MessageInput",
    "StreamEvent",
    "extract_content_parts",
    "message_to_openai",
    "messages_have_non_text_parts",
    "messages_to_openai",
    "normalize_messages",
]

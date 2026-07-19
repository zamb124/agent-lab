"""A2A/OpenAI-compatible message conversion for LLM clients."""

from __future__ import annotations

import base64
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Literal

from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from pydantic import Field

from core.a2a.codec import (
    mapping_from_struct,
    part_has_raw,
    part_has_text,
    struct_from_mapping,
)
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object

MessageInput = str | list[str] | Message | list[Message] | JsonObject | list[JsonObject]


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


def build_a2a_message(
    *,
    role: Role,
    parts: Sequence[Part],
    metadata: Mapping[str, JsonValue] | None = None,
    message_id: str | None = None,
) -> Message:
    """Собирает protobuf A2A `Message` с optional Struct metadata."""
    message = Message(
        message_id=message_id or str(uuid.uuid4()),
        role=role,
        parts=list(parts),
    )
    if metadata:
        message.metadata.CopyFrom(struct_from_mapping(metadata))
    return message


def extract_content_parts(parts: Sequence[Part | JsonObject]) -> tuple[list[JsonObject], bool]:
    """
    Извлекает content parts из списка A2A parts.

    Возвращает:
        Tuple (content_parts, has_files) где:
        - content_parts: список OpenAI content parts
        - has_files: True если есть файлы (нужен multimodal формат)
    """
    content_parts: list[JsonObject] = []
    has_files = False

    for part in parts:
        if isinstance(part, Part):
            if part_has_text(part):
                content_parts.append({"type": "text", "text": part.text})
                continue
            if part_has_raw(part):
                has_files = True
                mime_type = part.media_type if part.media_type else "image/png"
                b64_data = base64.b64encode(part.raw).decode("utf-8")
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    }
                )
                continue
            continue

        text = part.get("text")
        if isinstance(text, str) and part.get("raw") is None and part.get("url") is None:
            content_parts.append({"type": "text", "text": text})
            continue

        raw_value = part.get("raw")
        if isinstance(raw_value, str):
            has_files = True
            mime_value = part.get("mediaType") or part.get("media_type")
            mime_type = mime_value if isinstance(mime_value, str) and mime_value else "image/png"
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{raw_value}"},
                }
            )

    return content_parts, has_files


def message_to_openai(message: Message | JsonObject | str) -> JsonObject:
    """
    A2A Message в формат OpenAI API.

    Поддерживает:
    - Message объекты
    - dict (после десериализации из state)
    - строки
    - Multimodal: Part(text=...) + Part(raw=...)
    """
    role_map: dict[Role | str | int, str] = {
        Role.ROLE_USER: "user",
        Role.ROLE_AGENT: "assistant",
        "user": "user",
        "agent": "assistant",
        "assistant": "assistant",
        "ROLE_USER": "user",
        "ROLE_AGENT": "assistant",
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
            if (
                "ROLE_AGENT" in message
                or "role=<Role.ROLE_AGENT:" in message
                or "role='agent'" in message
            ):
                role_str = "assistant"

            return {"role": role_str, "content": content}

        return {"role": "user", "content": message}

    if isinstance(message, dict):
        role_raw = message.get("role", "user")
        role: Role | str | int = role_raw if isinstance(role_raw, (str, int)) else "user"
        metadata_raw = message.get("metadata")
        metadata = (
            require_json_object(metadata_raw, "message.metadata")
            if metadata_raw is not None
            else {}
        )
        parts_raw = message.get("parts", [])
        parts = (
            [
                require_json_object(part, "message.parts[]")
                for part in parts_raw
                if isinstance(part, dict)
            ]
            if isinstance(parts_raw, list)
            else []
        )

        content_value = message.get("content")
        if content_value:
            if not isinstance(content_value, (str, list)):
                raise ValueError("message.content must be a string or list of content parts")
            return {
                "role": role_map.get(role, str(role)),
                "content": content_value,
            }
    else:
        role = message.role
        metadata = mapping_from_struct(message.metadata) if message.metadata else {}
        parts = list(message.parts)

    content_parts, has_files = extract_content_parts(parts)
    if has_files:
        content: JsonValue = content_parts
    else:
        text_chunks: list[str] = []
        for content_part in content_parts:
            text = content_part.get("text")
            if content_part.get("type") == "text" and isinstance(text, str):
                text_chunks.append(text)
        content = "".join(text_chunks)

    is_system = metadata.get("system", False)
    openai_role = "system" if is_system else role_map.get(role, "user")
    if metadata.get("tool_call_id"):
        openai_role = "tool"

    openai_message: JsonObject = {
        "role": openai_role,
        "content": content,
    }

    if metadata.get("tool_calls"):
        openai_message["tool_calls"] = metadata["tool_calls"]

    if metadata.get("tool_call_id"):
        openai_message["tool_call_id"] = metadata["tool_call_id"]

    return openai_message


def messages_to_openai(messages: Sequence[Message | JsonObject | str]) -> list[JsonObject]:
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
            build_a2a_message(
                role=Role.ROLE_USER,
                parts=[Part(text=messages)],
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
            build_a2a_message(
                role=role,
                parts=[Part(text=content)],
                metadata=metadata or None,
            )
        ]

    if not messages:
        return []

    first = messages[0]

    if isinstance(first, str):
        string_messages: list[Message] = []
        for message_index, text in enumerate(messages):
            if not isinstance(text, str):
                raise ValueError("messages list must contain only strings")
            role = Role.ROLE_USER if message_index % 2 == 0 else Role.ROLE_AGENT
            string_messages.append(
                build_a2a_message(
                    role=role,
                    parts=[Part(text=text)],
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

    dict_messages: list[Message] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("messages list must contain only dict objects")
        role, metadata = _role_and_metadata_from_openai_dict(message)
        content = message.get("content", "")
        if not isinstance(content, str):
            raise ValueError("message.content must be string")
        dict_messages.append(
            build_a2a_message(
                role=role,
                parts=[Part(text=content)],
                metadata=metadata or None,
            )
        )
    return dict_messages


def _role_and_metadata_from_openai_dict(message: JsonObject) -> tuple[Role, JsonObject]:
    role_raw = str(message.get("role", "user"))
    metadata: JsonObject = {}
    if role_raw == "system":
        metadata["system"] = True
        return Role.ROLE_USER, metadata
    if role_raw == "tool":
        tool_call_id = message.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        return Role.ROLE_AGENT, metadata
    tool_calls = message.get("tool_calls")
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    if role_raw in ("assistant", "agent", "ROLE_AGENT"):
        return Role.ROLE_AGENT, metadata
    return Role.ROLE_USER, metadata


def messages_have_non_text_parts(openai_messages: list[JsonObject]) -> bool:
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
    "LLMToolCall",
    "LLMToolCallFunction",
    "build_a2a_message",
    "extract_content_parts",
    "message_to_openai",
    "messages_have_non_text_parts",
    "messages_to_openai",
    "normalize_messages",
]

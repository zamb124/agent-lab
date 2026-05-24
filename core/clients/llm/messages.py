"""A2A/OpenAI-compatible message conversion for LLM clients."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Literal

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


def extract_content_parts(parts: Sequence[Part | JsonObject]) -> tuple[list[JsonObject], bool]:
    """
    Извлекает content parts из списка A2A parts.

    Returns:
        Tuple (content_parts, has_files) где:
        - content_parts: список OpenAI content parts
        - has_files: True если есть файлы (нужен multimodal формат)
    """
    content_parts: list[JsonObject] = []
    has_files = False

    for part in parts:
        if isinstance(part, Part):
            root = part.root
            if isinstance(root, TextPart):
                content_parts.append({"type": "text", "text": root.text})
                continue
            if isinstance(root, FilePart):
                has_files = True
                file_obj = root.file
                if not isinstance(file_obj, FileWithBytes):
                    continue
                mime_type = file_obj.mime_type or "image/png"
                b64_data = file_obj.bytes
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    }
                )
                continue
            continue

        root_value = part.get("root", part)
        if not isinstance(root_value, dict):
            continue
        root_object = require_json_object(root_value, "message.part.root")
        text = root_object.get("text")
        if isinstance(text, str):
            content_parts.append({"type": "text", "text": text})
            continue

        file_value = root_object.get("file")
        if isinstance(file_value, dict):
            has_files = True
            file_object = require_json_object(file_value, "message.part.file")
            b64_data = file_object.get("bytes")
            if not isinstance(b64_data, str):
                continue
            mime_value = file_object.get("mimeType") or file_object.get("mime_type")
            mime_type = mime_value if isinstance(mime_value, str) and mime_value else "image/png"
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
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
        role = role_raw if isinstance(role_raw, str) else "user"
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
        metadata = (
            require_json_object(message.metadata, "message.metadata")
            if message.metadata
            else {}
        )
        parts = message.parts

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


def _role_and_metadata_from_openai_dict(message: JsonObject) -> tuple[Role, JsonObject]:
    role_raw = str(message.get("role", "user"))
    metadata: JsonObject = {}
    if role_raw == "system":
        metadata["system"] = True
        return Role.user, metadata
    if role_raw == "tool":
        tool_call_id = message.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        return Role.agent, metadata
    tool_calls = message.get("tool_calls")
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    if role_raw in ("assistant", "agent"):
        return Role.agent, metadata
    return Role.user, metadata


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
    "extract_content_parts",
    "message_to_openai",
    "messages_have_non_text_parts",
    "messages_to_openai",
    "normalize_messages",
]

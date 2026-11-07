"""A2A/OpenAI-compatible message conversion for LLM clients."""

from __future__ import annotations

import base64
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Literal, TypedDict

from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from pydantic import Field, TypeAdapter, ValidationError

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


class OpenAIImageUrlPayload(TypedDict):
    url: str


class OpenAITextContentPart(TypedDict):
    type: Literal["text"]
    text: str


class OpenAIImageContentPart(TypedDict):
    type: Literal["image_url"]
    image_url: OpenAIImageUrlPayload


OpenAIContentPart = OpenAITextContentPart | OpenAIImageContentPart

_OPENAI_CONTENT_PARTS_ADAPTER: TypeAdapter[list[OpenAIContentPart]] = TypeAdapter(
    list[OpenAIContentPart]
)


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


def extract_content_parts(
    parts: Sequence[Part | JsonObject],
) -> tuple[list[OpenAIContentPart], bool]:
    """A2A parts → OpenAI content parts; has_files=True при наличии raw/image."""
    content_parts: list[OpenAIContentPart] = []
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


def _require_openai_content_parts(content: JsonValue, field_name: str) -> list[OpenAIContentPart]:
    """Граница JSON → OpenAI content parts; неизвестный shape — raise."""
    try:
        return _OPENAI_CONTENT_PARTS_ADAPTER.validate_python(content)
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be OpenAI content parts") from exc


def _openai_content_as_json(parts: list[OpenAIContentPart], field_name: str) -> JsonValue:
    return [
        require_json_object(part, f"{field_name}[{index}]")
        for index, part in enumerate(parts)
    ]


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
        message_content: JsonValue = _openai_content_as_json(
            content_parts, "openai.content"
        )
    else:
        message_content = "".join(
            part["text"] for part in content_parts if part["type"] == "text"
        )

    is_system = metadata.get("system", False)
    openai_role = "system" if is_system else role_map.get(role, "user")
    if metadata.get("tool_call_id"):
        openai_role = "tool"

    openai_message: JsonObject = {
        "role": openai_role,
        "content": message_content,
    }

    if metadata.get("tool_calls"):
        openai_message["tool_calls"] = metadata["tool_calls"]

    if metadata.get("tool_call_id"):
        openai_message["tool_call_id"] = metadata["tool_call_id"]

    return openai_message


def _expand_openai_tool_multimodal(openai_message: JsonObject) -> list[JsonObject]:
    """Chat Completions: role=tool только text; image_url → следующее user с interleaved labels.

    A2A tool-result: Part(text=envelope), Part(text='Image p0_n1:'), Part(raw), …
    Wire: tool(content=envelope) + user(content=[text label, image_url, …]).
    """
    if openai_message.get("role") != "tool":
        return [openai_message]
    content = openai_message.get("content")
    if not isinstance(content, list):
        return [openai_message]

    parts = _require_openai_content_parts(content, "openai.tool.content")
    if not parts:
        raise ValueError("openai.tool.content must be non-empty")
    first = parts[0]
    if first["type"] != "text":
        raise ValueError("multimodal tool message must start with a text content part")
    if not any(part["type"] == "image_url" for part in parts):
        raise ValueError("openai.tool.content list must include image_url")

    expanded: list[JsonObject] = [
        {
            "role": "tool",
            "tool_call_id": openai_message["tool_call_id"],
            "content": first["text"],
        }
    ]
    vision_content = parts[1:]
    if vision_content:
        expanded.append(
            {
                "role": "user",
                "content": _openai_content_as_json(
                    vision_content, "openai.tool.vision"
                ),
            }
        )
    return expanded


def messages_to_openai(messages: Sequence[Message | JsonObject | str]) -> list[JsonObject]:
    """Список A2A Message → OpenAI Chat Completions; multimodal tool → tool text + user images."""
    openai_messages: list[JsonObject] = []
    for message in messages:
        openai_messages.extend(_expand_openai_tool_multimodal(message_to_openai(message)))
    return openai_messages


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
        for part in _require_openai_content_parts(content, "openai.message.content"):
            if part["type"] != "text":
                return True
    return False


__all__ = [
    "MessageInput",
    "StreamEvent",
    "LLMToolCall",
    "LLMToolCallFunction",
    "OpenAIContentPart",
    "OpenAIImageContentPart",
    "OpenAIImageUrlPayload",
    "OpenAITextContentPart",
    "build_a2a_message",
    "extract_content_parts",
    "message_to_openai",
    "messages_have_non_text_parts",
    "messages_to_openai",
    "normalize_messages",
]

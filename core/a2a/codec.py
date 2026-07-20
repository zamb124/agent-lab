"""Codec для A2A protobuf Message/Part/Struct ↔ JSON dict."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from a2a.types import Message, Part
from google.protobuf.json_format import MessageToDict, Parse, ParseDict
from google.protobuf.struct_pb2 import Struct, Value

from core.types import JsonObject, JsonValue, require_json_object, require_json_value

_PART_CONTENT_ONEOF = "content"

# Wire-дискриминаторы A2A JSON Schema / 0.3 — не поля protobuf Message/Part.
_WIRE_KIND_KEY = "kind"
_MESSAGE_WIRE_KIND = "message"

_ROLE_ALIASES: dict[str, str] = {
    "user": "ROLE_USER",
    "USER": "ROLE_USER",
    "ROLE_USER": "ROLE_USER",
    "agent": "ROLE_AGENT",
    "AGENT": "ROLE_AGENT",
    "assistant": "ROLE_AGENT",
    "ROLE_AGENT": "ROLE_AGENT",
    "system": "ROLE_UNSPECIFIED",
    "SYSTEM": "ROLE_UNSPECIFIED",
    "ROLE_UNSPECIFIED": "ROLE_UNSPECIFIED",
}


def message_to_json_dict(message: Message) -> JsonObject:
    """Сериализует protobuf `Message` в ProtoJSON dict (camelCase)."""
    return require_json_object(MessageToDict(message), "Message")


def _normalize_part_json(part: JsonObject) -> JsonObject:
    """Убирает wire `kind` у Part и null-поля; оставляет ProtoJSON oneof content."""
    normalized: JsonObject = {}
    for key, value in part.items():
        if key == _WIRE_KIND_KEY:
            continue
        if value is None:
            continue
        normalized[key] = value
    return normalized


def _normalize_message_role(raw_role: JsonValue) -> str:
    if not isinstance(raw_role, str) or raw_role.strip() == "":
        raise ValueError("Message.role required")
    mapped = _ROLE_ALIASES.get(raw_role.strip())
    if mapped is None:
        raise ValueError(f"Unsupported Message.role: {raw_role!r}")
    return mapped


def normalize_message_json_for_proto(payload: Mapping[str, JsonValue]) -> JsonObject:
    """Нормализует ProtoJSON / historical A2A JSON Message к форме для ParseDict.

    Исторические ledger/Redis projection могут содержать 0.3-дискриминаторы
    (`kind: message`, `parts[].kind`, `role: user`). Protobuf Message их не имеет.
    """
    normalized: JsonObject = {}
    for key, value in payload.items():
        if key == _WIRE_KIND_KEY:
            if value is not None and value != _MESSAGE_WIRE_KIND:
                raise ValueError(f"Unsupported Message.kind: {value!r}")
            continue
        if value is None:
            continue
        if key == "role":
            normalized[key] = _normalize_message_role(value)
            continue
        if key == "parts":
            if not isinstance(value, list):
                raise ValueError("Message.parts must be a list")
            parts: list[JsonValue] = []
            for index, entry in enumerate(value):
                if not isinstance(entry, dict):
                    raise ValueError(f"Message.parts[{index}] must be an object")
                part_obj = require_json_object(entry, f"Message.parts[{index}]")
                parts.append(_normalize_part_json(part_obj))
            normalized[key] = parts
            continue
        normalized[key] = value
    return normalized


def message_from_json_dict(payload: Mapping[str, JsonValue]) -> Message:
    """Десериализует ProtoJSON (и historical 0.3-shaped) dict в protobuf `Message`."""
    message = Message()
    _ = ParseDict(normalize_message_json_for_proto(payload), message)
    return message


def struct_from_mapping(mapping: Mapping[str, JsonValue]) -> Struct:
    """Собирает `google.protobuf.Struct` из JSON object."""
    struct = Struct()
    _ = ParseDict(dict(mapping), struct)
    return struct


def mapping_from_struct(struct: Struct) -> JsonObject:
    """Разворачивает `Struct` в JSON object."""
    return require_json_object(MessageToDict(struct), "Struct")


def value_from_json(value: JsonValue) -> Value:
    """Оборачивает JSON value в `google.protobuf.Value`."""
    proto_value = Value()
    _ = Parse(json.dumps(value), proto_value)
    return proto_value


def json_from_value(value: Value) -> JsonValue:
    """Разворачивает `google.protobuf.Value` в JSON value."""
    return require_json_value(MessageToDict(value), "Value")


def _part_content_kind(part: Part) -> str | None:
    kind = cast(str | None, part.WhichOneof(_PART_CONTENT_ONEOF))
    return kind


def part_has_text(part: Part) -> bool:
    return _part_content_kind(part) == "text"


def part_has_raw(part: Part) -> bool:
    return _part_content_kind(part) == "raw"


def part_has_url(part: Part) -> bool:
    return _part_content_kind(part) == "url"


def part_has_data(part: Part) -> bool:
    return _part_content_kind(part) == "data"


def get_part_text(part: Part) -> str:
    if not part_has_text(part):
        raise ValueError(f"Part has no text content: {_part_content_kind(part)!r}")
    return part.text


def get_part_raw(part: Part) -> bytes:
    if not part_has_raw(part):
        raise ValueError(f"Part has no raw content: {_part_content_kind(part)!r}")
    return part.raw


def get_part_url(part: Part) -> str:
    if not part_has_url(part):
        raise ValueError(f"Part has no url content: {_part_content_kind(part)!r}")
    return part.url


def get_part_data(part: Part) -> JsonValue:
    if not part_has_data(part):
        raise ValueError(f"Part has no data content: {_part_content_kind(part)!r}")
    return json_from_value(part.data)


def messages_from_json_list(items: Sequence[object]) -> list[Message]:
    """Нормализует list[Message|dict] в list[Message] (для Pydantic validators)."""
    result: list[Message] = []
    for item in items:
        if isinstance(item, Message):
            result.append(item)
        elif isinstance(item, dict):
            payload = require_json_object(cast(JsonObject, item), "Message")
            result.append(message_from_json_dict(payload))
        else:
            raise ValueError(f"Ожидается Message или dict, получен {type(item)}")
    return result


def messages_to_json_list(messages: Sequence[Message]) -> list[JsonObject]:
    return [message_to_json_dict(message) for message in messages]


__all__ = [
    "message_to_json_dict",
    "message_from_json_dict",
    "normalize_message_json_for_proto",
    "struct_from_mapping",
    "mapping_from_struct",
    "value_from_json",
    "json_from_value",
    "part_has_text",
    "part_has_raw",
    "part_has_url",
    "part_has_data",
    "get_part_text",
    "get_part_raw",
    "get_part_url",
    "get_part_data",
    "messages_from_json_list",
    "messages_to_json_list",
]

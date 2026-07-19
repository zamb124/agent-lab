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


def message_to_json_dict(message: Message) -> JsonObject:
    """Сериализует protobuf `Message` в ProtoJSON dict (camelCase)."""
    return require_json_object(MessageToDict(message), "Message")


def message_from_json_dict(payload: Mapping[str, JsonValue]) -> Message:
    """Десериализует ProtoJSON dict в protobuf `Message`."""
    message = Message()
    _ = ParseDict(dict(payload), message)
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

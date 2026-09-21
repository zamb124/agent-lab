"""Codec для A2A protobuf Message/Part/Struct ↔ JSON dict."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from a2a.types import (
    Artifact,
    Message,
    Part,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import MessageToDict, Parse, ParseDict
from google.protobuf.struct_pb2 import Struct, Value

from core.types import JsonObject, JsonValue, require_json_object, require_json_value

_STREAM_RESPONSE_WIRE_KEYS = ("task", "message", "statusUpdate", "artifactUpdate")

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
    raw = require_json_object(MessageToDict(message), "Message")
    return require_json_object(_restore_json_integers(raw), "Message")


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


def normalize_artifact_json_for_proto(payload: Mapping[str, JsonValue]) -> JsonObject:
    """Normalize an Artifact payload while retaining every standard field."""
    normalized: JsonObject = {}
    for key, value in payload.items():
        if value is None:
            continue
        if key == "parts":
            if not isinstance(value, list):
                raise ValueError("Artifact.parts must be a list")
            parts: list[JsonValue] = []
            for index, entry in enumerate(value):
                if not isinstance(entry, dict):
                    raise ValueError(f"Artifact.parts[{index}] must be an object")
                parts.append(
                    _normalize_part_json(
                        require_json_object(entry, f"Artifact.parts[{index}]")
                    )
                )
            normalized[key] = parts
            continue
        normalized[key] = value
    return normalized


def artifact_to_json_dict(artifact: Artifact) -> JsonObject:
    return require_json_object(MessageToDict(artifact), "Artifact")


def artifact_from_json_dict(payload: Mapping[str, JsonValue]) -> Artifact:
    artifact = Artifact()
    _ = ParseDict(normalize_artifact_json_for_proto(payload), artifact)
    return artifact


def task_status_to_json_dict(status: TaskStatus) -> JsonObject:
    return require_json_object(MessageToDict(status), "TaskStatus")


def task_status_from_json_dict(payload: Mapping[str, JsonValue]) -> TaskStatus:
    normalized: JsonObject = dict(payload)
    message_value = normalized.get("message")
    if isinstance(message_value, dict):
        normalized["message"] = normalize_message_json_for_proto(
            require_json_object(message_value, "TaskStatus.message")
        )
    status = TaskStatus()
    _ = ParseDict(normalized, status)
    return status


def task_to_json_dict(task: Task) -> JsonObject:
    return require_json_object(MessageToDict(task), "Task")


def task_from_json_dict(payload: Mapping[str, JsonValue]) -> Task:
    normalized: JsonObject = dict(payload)
    status_value = normalized.get("status")
    if isinstance(status_value, dict):
        normalized["status"] = task_status_to_json_dict(
            task_status_from_json_dict(
                require_json_object(status_value, "Task.status")
            )
        )
    artifacts_value = normalized.get("artifacts")
    if isinstance(artifacts_value, list):
        normalized_artifacts: list[JsonValue] = []
        for index, artifact_value in enumerate(artifacts_value):
            if not isinstance(artifact_value, dict):
                raise ValueError(f"Task.artifacts[{index}] must be an object")
            normalized_artifacts.append(
                normalize_artifact_json_for_proto(
                    require_json_object(artifact_value, f"Task.artifacts[{index}]")
                )
            )
        normalized["artifacts"] = normalized_artifacts
    history_value = normalized.get("history")
    if isinstance(history_value, list):
        normalized_history: list[JsonValue] = []
        for index, message_value in enumerate(history_value):
            if not isinstance(message_value, dict):
                raise ValueError(f"Task.history[{index}] must be an object")
            normalized_history.append(
                normalize_message_json_for_proto(
                    require_json_object(message_value, f"Task.history[{index}]")
                )
            )
        normalized["history"] = normalized_history
    task = Task()
    _ = ParseDict(normalized, task)
    return task


def artifact_update_to_json_dict(event: TaskArtifactUpdateEvent) -> JsonObject:
    return require_json_object(MessageToDict(event), "TaskArtifactUpdateEvent")


def artifact_update_from_json_dict(
    payload: Mapping[str, JsonValue],
) -> TaskArtifactUpdateEvent:
    normalized: JsonObject = dict(payload)
    artifact_value = normalized.get("artifact")
    if isinstance(artifact_value, dict):
        normalized["artifact"] = normalize_artifact_json_for_proto(
            require_json_object(artifact_value, "TaskArtifactUpdateEvent.artifact")
        )
    event = TaskArtifactUpdateEvent()
    _ = ParseDict(normalized, event)
    return event


def status_update_to_json_dict(event: TaskStatusUpdateEvent) -> JsonObject:
    return require_json_object(MessageToDict(event), "TaskStatusUpdateEvent")


def status_update_from_json_dict(
    payload: Mapping[str, JsonValue],
) -> TaskStatusUpdateEvent:
    normalized: JsonObject = dict(payload)
    status_value = normalized.get("status")
    if isinstance(status_value, dict):
        normalized["status"] = task_status_to_json_dict(
            task_status_from_json_dict(
                require_json_object(status_value, "TaskStatusUpdateEvent.status")
            )
        )
    event = TaskStatusUpdateEvent()
    _ = ParseDict(normalized, event)
    return event


def struct_from_mapping(mapping: Mapping[str, JsonValue]) -> Struct:
    """Собирает `google.protobuf.Struct` из JSON object."""
    struct = Struct()
    _ = ParseDict(dict(mapping), struct)
    return struct


def _restore_json_integers(value: JsonValue) -> JsonValue:
    """protobuf Struct/Value хранит числа как double; MessageToDict отдаёт float.

    JSON integer (и tool args с schema integer) после round-trip должны снова
    быть int, иначе sandbox/f-string получают 30.0 вместо 30. Safe в пределах
    IEEE-754 exact integer range (±2^53).
    """
    if isinstance(value, float) and value.is_integer() and abs(value) <= 2**53:
        return int(value)
    if isinstance(value, list):
        return [_restore_json_integers(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _restore_json_integers(item)
            for key, item in value.items()
        }
    return value


def mapping_from_struct(struct: Struct) -> JsonObject:
    """Разворачивает `Struct` в JSON object."""
    raw = require_json_object(MessageToDict(struct), "Struct")
    restored = _restore_json_integers(raw)
    return require_json_object(restored, "Struct")


def value_from_json(value: JsonValue) -> Value:
    """Оборачивает JSON value в `google.protobuf.Value`."""
    proto_value = Value()
    _ = Parse(json.dumps(value), proto_value)
    return proto_value


def json_from_value(value: Value) -> JsonValue:
    """Разворачивает `google.protobuf.Value` в JSON value."""
    raw = require_json_value(MessageToDict(value), "Value")
    return _restore_json_integers(raw)

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
            raise ValueError(f"Expected Message or dict, got {type(item)}")
    return result


def messages_to_json_list(messages: Sequence[Message]) -> list[JsonObject]:
    return [message_to_json_dict(message) for message in messages]


def stream_response_from_event(
    event: Task | Message | TaskStatusUpdateEvent | TaskArtifactUpdateEvent,
) -> StreamResponse:
    """Wrap one A2A stream payload into the standard StreamResponse oneof."""
    if isinstance(event, TaskStatusUpdateEvent):
        return StreamResponse(status_update=event)
    if isinstance(event, TaskArtifactUpdateEvent):
        return StreamResponse(artifact_update=event)
    if isinstance(event, Task):
        return StreamResponse(task=event)
    return StreamResponse(message=event)


def stream_response_to_json_dict(stream: StreamResponse) -> JsonObject:
    """Serialize StreamResponse to ProtoJSON; payload oneof is required."""
    if not (
        stream.HasField("task")
        or stream.HasField("message")
        or stream.HasField("status_update")
        or stream.HasField("artifact_update")
    ):
        raise ValueError("StreamResponse payload oneof is required")
    return require_json_object(MessageToDict(stream), "StreamResponse")


def stream_response_from_json_dict(payload: Mapping[str, JsonValue]) -> StreamResponse:
    """Parse ProtoJSON StreamResponse; exactly one payload field must be present."""
    present = [key for key in _STREAM_RESPONSE_WIRE_KEYS if key in payload]
    if len(present) != 1:
        raise ValueError(
            f"StreamResponse requires exactly one of {_STREAM_RESPONSE_WIRE_KEYS}, got {present!r}"
        )
    stream = StreamResponse()
    _ = ParseDict(dict(payload), stream)
    if not (
        stream.HasField("task")
        or stream.HasField("message")
        or stream.HasField("status_update")
        or stream.HasField("artifact_update")
    ):
        raise ValueError("StreamResponse payload oneof is required after parse")
    return stream


__all__ = [
    "artifact_from_json_dict",
    "artifact_to_json_dict",
    "artifact_update_from_json_dict",
    "artifact_update_to_json_dict",
    "message_to_json_dict",
    "message_from_json_dict",
    "normalize_message_json_for_proto",
    "normalize_artifact_json_for_proto",
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
    "status_update_from_json_dict",
    "status_update_to_json_dict",
    "stream_response_from_event",
    "stream_response_from_json_dict",
    "stream_response_to_json_dict",
    "task_from_json_dict",
    "task_status_from_json_dict",
    "task_status_to_json_dict",
    "task_to_json_dict",
]

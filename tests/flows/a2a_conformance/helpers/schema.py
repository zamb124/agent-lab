"""Validate payloads against pinned official A2A fixtures / protobuf types."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from a2a.types import AgentCard, Message, Part, StreamResponse, Task, TaskState
from google.protobuf.json_format import ParseDict
from google.protobuf.message import DecodeError
from google.protobuf.message import Message as ProtoMessage

from core.types import JsonObject, require_json_object

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "official"
OFFICIAL_JSON_SCHEMA_PATH = FIXTURES_DIR / "a2a.json"
OFFICIAL_PROTO_PATH = FIXTURES_DIR / "a2a.proto"
OFFICIAL_VERSION_PATH = FIXTURES_DIR / "VERSION"


def load_official_version() -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in OFFICIAL_VERSION_PATH.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key] = value
    if parsed.get("protocol_version") != "1.0":
        raise AssertionError(f"Pinned fixtures must be protocol 1.0, got {parsed!r}")
    return parsed


def load_official_json_schema() -> JsonObject:
    return require_json_object(
        json.loads(OFFICIAL_JSON_SCHEMA_PATH.read_text(encoding="utf-8")),
        "a2a.json",
    )


def _parse_proto(message: ProtoMessage, payload: Mapping[str, object], label: str) -> None:
    try:
        _ = ParseDict(dict(payload), message, ignore_unknown_fields=False)
    except (DecodeError, TypeError, ValueError) as exc:
        raise AssertionError(f"{label} is not valid A2A 1.0 ProtoJSON: {exc}") from exc


def assert_valid_agent_card(payload: Mapping[str, object]) -> AgentCard:
    # Platform extensions (branches/variables) — strip before proto parse; skills stays.
    cleaned = {
        key: value
        for key, value in payload.items()
        if key not in {"branches", "variables"}
    }
    if "skills" not in cleaned:
        raise AssertionError("AgentCard.skills is required for A2A 1.0")
    card = AgentCard()
    try:
        _ = ParseDict(cleaned, card, ignore_unknown_fields=False)
    except (DecodeError, TypeError, ValueError) as exc:
        raise AssertionError(f"AgentCard is not valid A2A 1.0 ProtoJSON: {exc}") from exc
    if not card.name:
        raise AssertionError("AgentCard.name is required")
    if not card.skills:
        raise AssertionError("AgentCard.skills must be a non-empty list for A2A 1.0")
    if not card.supported_interfaces:
        raise AssertionError("AgentCard.supportedInterfaces is required for A2A 1.0")
    versions = {iface.protocol_version for iface in card.supported_interfaces}
    if "1.0" not in versions:
        raise AssertionError(f"AgentCard must declare protocolVersion 1.0, got {versions!r}")
    return card


def assert_valid_message(payload: Mapping[str, object]) -> Message:
    message = Message()
    _parse_proto(message, payload, "Message")
    if not message.message_id:
        raise AssertionError("Message.messageId is required")
    if not message.parts:
        raise AssertionError("Message.parts is required")
    for part in message.parts:
        assert_valid_part_proto(part)
    return message


def assert_valid_part_proto(part: Part) -> None:
    kind = part.WhichOneof("content")
    if kind is None:
        raise AssertionError("Part must contain exactly one of text|raw|url|data")


def assert_valid_part_dict(payload: Mapping[str, object]) -> Part:
    if "kind" in payload:
        raise AssertionError("A2A 1.0 Part must not include legacy kind discriminator")
    part = Part()
    _parse_proto(part, payload, "Part")
    assert_valid_part_proto(part)
    return part


def assert_valid_task(payload: Mapping[str, object]) -> Task:
    task = Task()
    _parse_proto(task, payload, "Task")
    if not task.id:
        raise AssertionError("Task.id is required")
    if task.HasField("status"):
        state_name = TaskState.Name(task.status.state)
        if not state_name.startswith("TASK_STATE_"):
            raise AssertionError(f"Task.status.state must be TASK_STATE_*, got {state_name!r}")
    return task


def assert_valid_stream_result(payload: Mapping[str, object]) -> StreamResponse:
    if "kind" in payload:
        raise AssertionError("A2A 1.0 StreamResponse must not use legacy kind field")
    stream = StreamResponse()
    _parse_proto(stream, payload, "StreamResponse")
    which = stream.WhichOneof("payload")
    if which is None:
        raise AssertionError("StreamResponse must set task|message|statusUpdate|artifactUpdate")
    return stream


def assert_no_legacy_0_3_keys(payload: Mapping[str, object]) -> None:
    forbidden = {"kind", "fileWithBytes", "fileWithUri", "mimeType"}
    found = forbidden.intersection(payload)
    if found:
        raise AssertionError(f"Legacy A2A 0.3 keys forbidden in 1.0 payload: {sorted(found)}")

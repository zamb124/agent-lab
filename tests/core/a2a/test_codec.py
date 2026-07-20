"""Unit: A2A Message codec — ProtoJSON 1.0 + historical 0.3-shaped ledger payloads."""

from __future__ import annotations

import pytest
from a2a.types.a2a_pb2 import ROLE_AGENT, ROLE_USER
from google.protobuf.json_format import ParseError

from core.a2a.codec import (
    get_part_text,
    message_from_json_dict,
    message_to_json_dict,
    messages_from_json_list,
    normalize_message_json_for_proto,
)


def test_message_from_protojson_roundtrip() -> None:
    payload = {
        "messageId": "m1",
        "role": "ROLE_USER",
        "parts": [{"text": "hello"}],
        "contextId": "ctx",
        "taskId": "tid",
    }
    message = message_from_json_dict(payload)
    assert message.role == ROLE_USER
    assert get_part_text(message.parts[0]) == "hello"
    dumped = message_to_json_dict(message)
    assert dumped["messageId"] == "m1"
    assert dumped["role"] == "ROLE_USER"
    assert "kind" not in dumped


def test_message_from_historical_0_3_shaped_ledger_payload() -> None:
    """Исторический state_delta HITL: kind + role=user + parts[].kind."""
    historical = {
        "kind": "message",
        "role": "user",
        "parts": [
            {
                "kind": "text",
                "text": "оператор",
                "metadata": None,
            }
        ],
        "taskId": "01cf250e-f127-4343-907a-7adcc5416474",
        "metadata": {"node_id": "hitl_queue_demo"},
        "contextId": "1784024894138",
        "messageId": "hitl-user-input:01cf250e-f127-4343-907a-7adcc5416474",
        "extensions": None,
        "referenceTaskIds": None,
    }
    message = message_from_json_dict(historical)
    assert message.role == ROLE_USER
    assert message.message_id == "hitl-user-input:01cf250e-f127-4343-907a-7adcc5416474"
    assert get_part_text(message.parts[0]) == "оператор"


def test_messages_from_json_list_accepts_historical_batch() -> None:
    items = [
        {
            "kind": "message",
            "role": "agent",
            "parts": [{"kind": "text", "text": "reply"}],
            "messageId": "m2",
        }
    ]
    messages = messages_from_json_list(items)
    assert len(messages) == 1
    assert messages[0].role == ROLE_AGENT
    assert get_part_text(messages[0].parts[0]) == "reply"


def test_normalize_rejects_unknown_message_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported Message.kind"):
        _ = normalize_message_json_for_proto({"kind": "task", "role": "ROLE_USER", "parts": []})


def test_normalize_rejects_unknown_role() -> None:
    with pytest.raises(ValueError, match="Unsupported Message.role"):
        _ = normalize_message_json_for_proto({"role": "tool", "parts": []})


def test_message_from_json_still_rejects_unknown_proto_fields() -> None:
    with pytest.raises(ParseError):
        _ = message_from_json_dict(
            {
                "messageId": "m3",
                "role": "ROLE_USER",
                "parts": [{"text": "x"}],
                "notAField": True,
            }
        )

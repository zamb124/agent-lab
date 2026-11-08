"""Unit: A2A Message codec — ProtoJSON 1.0 + historical 0.3-shaped ledger payloads."""

from __future__ import annotations

import pytest
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import (
    Artifact,
    ListTaskPushNotificationConfigsResponse,
    ListTasksResponse,
    Message,
    Part,
    Role,
    StreamResponse,
    Task,
    TaskState,
    TaskStatus,
)
from a2a.types.a2a_pb2 import ROLE_AGENT, ROLE_USER
from google.protobuf.json_format import ParseError

from core.a2a.codec import (
    artifact_from_json_dict,
    artifact_to_json_dict,
    get_part_text,
    message_from_json_dict,
    message_to_json_dict,
    messages_from_json_list,
    normalize_message_json_for_proto,
    rpc_result_to_json_dict,
    stream_response_from_event,
    stream_response_from_json_dict,
    stream_response_to_json_dict,
    task_from_json_dict,
    task_to_json_dict,
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


def test_artifact_codec_round_trips_mixed_parts_metadata_and_extensions() -> None:
    artifact = Artifact(
        artifact_id="artifact-1",
        name="custom",
        description="mixed",
        parts=[
            new_text_part("text"),
            Part(raw=b"raw", filename="raw.bin", media_type="application/octet-stream"),
            Part(url="https://files.linnex.io/download/1"),
            new_data_part({"nested": {"value": True}}),
        ],
        extensions=["https://linnex.io/a2a/extensions/example/v1"],
    )

    dumped = artifact_to_json_dict(artifact)
    restored = artifact_from_json_dict(dumped)

    assert artifact_to_json_dict(restored) == dumped


def test_task_codec_round_trips_complete_lossless_snapshot() -> None:
    task = Task(
        id="task-1",
        context_id="context-1",
        status=TaskStatus(
            state=TaskState.TASK_STATE_COMPLETED,
            message=Message(
                message_id="agent-1",
                role=Role.ROLE_AGENT,
                parts=[new_text_part("done")],
            ),
        ),
        artifacts=[
            Artifact(
                artifact_id="artifact-1",
                name="custom",
                parts=[new_data_part({"value": 1})],
            )
        ],
        history=[
            Message(
                message_id="user-1",
                role=Role.ROLE_USER,
                parts=[new_text_part("start")],
            )
        ],
    )

    dumped = task_to_json_dict(task)
    restored = task_from_json_dict(dumped)

    assert task_to_json_dict(restored) == dumped


def test_stream_response_codec_requires_exactly_one_payload() -> None:
    task = Task(
        id="task-1",
        context_id="context-1",
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    )
    stream = stream_response_from_event(task)
    dumped = stream_response_to_json_dict(stream)
    assert "task" in dumped
    restored = stream_response_from_json_dict(dumped)
    assert restored.HasField("task")
    assert restored.task.id == "task-1"

    with pytest.raises(ValueError, match="exactly one"):
        _ = stream_response_from_json_dict({})

    empty = StreamResponse()
    with pytest.raises(ValueError, match="payload oneof is required"):
        _ = stream_response_to_json_dict(empty)


def test_rpc_result_restores_required_empty_list_fields() -> None:
    """ProtoJSON опускает пустые repeated/string; wire-контракт требует их присутствия.

    flow-ui клиент падает с "ListTasks result.tasks must be an array", когда
    `tasks` отсутствует в ответе на пустой контекст.
    """
    dumped = rpc_result_to_json_dict(ListTasksResponse())
    assert dumped == {"tasks": [], "nextPageToken": ""}

    cfg_dumped = rpc_result_to_json_dict(ListTaskPushNotificationConfigsResponse())
    assert cfg_dumped == {"configs": [], "nextPageToken": ""}


def test_rpc_result_preserves_nonempty_list_fields() -> None:
    task = Task(
        id="task-1",
        context_id="context-1",
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    )
    dumped = rpc_result_to_json_dict(
        ListTasksResponse(tasks=[task], next_page_token="7", page_size=50, total_size=1)
    )
    assert len(dumped["tasks"]) == 1
    assert dumped["tasks"][0]["id"] == "task-1"
    assert dumped["nextPageToken"] == "7"


def test_rpc_result_leaves_other_messages_untouched() -> None:
    message = Message(
        message_id="m1",
        role=Role.ROLE_USER,
        parts=[new_text_part("hi")],
    )
    dumped = rpc_result_to_json_dict(message)
    assert "tasks" not in dumped
    assert "nextPageToken" not in dumped
    assert dumped["messageId"] == "m1"

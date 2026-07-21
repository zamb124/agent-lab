"""
LlmNode + MockLLM matrix for gdocs_* against Google API emulator.

Мок только MockLLM. Live Google: test_google_docs_integration.py (-m network).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from a2a.helpers.proto_helpers import get_message_text

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from core.clients.google_docs_client import GoogleDocsClient
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from tests.fixtures.google_api_emulator import GoogleApiEmulatorHandle
from tests.flows.durable_runtime_harness import ensure_workflow_started


@pytest.fixture()
def gdocs_client(google_api_emulator: GoogleApiEmulatorHandle) -> GoogleDocsClient:
    return GoogleDocsClient(access_token=google_api_emulator.oauth_token)


def _make_state(
    unique_id: str,
    flow_id: str,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> ExecutionState:
    context_id = f"ctx-gdocs-emu-llm-{unique_id}"
    return ExecutionState(
        task_id=f"task-gdocs-emu-llm-{unique_id}",
        context_id=context_id,
        user_id=f"user-gdocs-emu-llm-{unique_id}",
        session_id=f"{flow_id}:{context_id}",
        content="Выполни",
        variables={"google_access_token": google_api_emulator.oauth_token},
    )


def _parse_tool_payload(content: object) -> JsonObject:
    if isinstance(content, dict):
        return require_json_object(content, "gdocs.tool_message")
    if isinstance(content, str):
        return require_json_object(json.loads(content), "gdocs.tool_message")
    raise TypeError(f"unexpected tool content type: {type(content).__name__}")


def _metadata_tool_call_id(metadata: object) -> object | None:
    """tool_call_id из dict или protobuf Struct (A2A Message.metadata)."""
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get("tool_call_id")
    try:
        if "tool_call_id" not in metadata:
            return None
        return metadata["tool_call_id"]
    except TypeError:
        return None


def _message_is_tool(message: object) -> bool:
    # A2A Message: и tool-result, и финальный assistant text могут иметь один role —
    # отличить можно только по metadata.tool_call_id.
    if isinstance(message, dict):
        if _metadata_tool_call_id(message.get("metadata")):
            return True
        return message.get("role") == "tool"
    return _metadata_tool_call_id(getattr(message, "metadata", None)) is not None



def _message_text(message: object) -> str:
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        return ""
    return get_message_text(message)


def _tool_payloads_from_state(state: ExecutionState) -> list[JsonObject]:
    return [
        _parse_tool_payload(_message_text(message))
        for message in state.messages
        if _message_is_tool(message)
    ]


async def _run_single_tool_flow(
    unique_id: str,
    flow_suffix: str,
    tool_ids: list[str],
    tool_call_name: str,
    tool_call_args: dict[str, Any],
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> tuple[dict[str, Any], ExecutionState]:
    flow_id = f"gdocs_emu_{flow_suffix}_{unique_id}"
    container = get_container()
    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"GDocs emu {flow_suffix}",
        entry="agent",
        nodes={
            "agent": {
                "type": "llm_node",
                "prompt": "Ты агент для Google Docs.",
                "tools": [{"tool_id": tid} for tid in tool_ids],
            }
        },
        edges=[],
    )
    await container.flow_repository.set(flow_config)
    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": tool_call_name, "args": tool_call_args},
            {"type": "text", "content": "Готово."},
        ]
    )
    flow = await container.flow_factory.get_flow(flow_id)
    state = _make_state(unique_id, flow_id, google_api_emulator)
    await ensure_workflow_started(
        container=container,
        state=state,
        flow_id=flow_id,
        branch_id=state.branch_id,
    )
    final_state = await flow.run(state)
    await container.flow_repository.delete(flow_id)
    return final_state, final_state


@pytest.mark.asyncio
async def test_create_document_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> None:
    _ = app
    result, state = await _run_single_tool_flow(
        unique_id,
        "create",
        ["gdocs_create_document"],
        "gdocs_create_document",
        {"title": f"Agent Doc {unique_id}"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert payload["success"] is True
    assert isinstance(payload["document_id"], str)


@pytest.mark.asyncio
async def test_read_append_insert_find_delete_share_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
    gdocs_client: GoogleDocsClient,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"Ops {unique_id}")
    doc_id = str(doc["documentId"])
    await gdocs_client.append_text(doc_id, "Hello world.")

    _, state = await _run_single_tool_flow(
        f"{unique_id}-read",
        "read",
        ["gdocs_read_document"],
        "gdocs_read_document",
        {"document_id": doc_id},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert "Hello world." in str(_tool_payloads_from_state(state)[0]["text"])

    _, state = await _run_single_tool_flow(
        f"{unique_id}-ap",
        "append",
        ["gdocs_append_text"],
        "gdocs_append_text",
        {"document_id": doc_id, "text": " More."},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["success"] is True

    _, state = await _run_single_tool_flow(
        f"{unique_id}-in",
        "insert",
        ["gdocs_insert_text"],
        "gdocs_insert_text",
        {"document_id": doc_id, "text": "X", "index": 1},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["success"] is True

    _, state = await _run_single_tool_flow(
        f"{unique_id}-fr",
        "fr",
        ["gdocs_find_replace"],
        "gdocs_find_replace",
        {"document_id": doc_id, "find": "world", "replace": "planet"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert "occurrences_changed" in _tool_payloads_from_state(state)[0]

    _, state = await _run_single_tool_flow(
        f"{unique_id}-del",
        "del",
        ["gdocs_delete_range"],
        "gdocs_delete_range",
        {"document_id": doc_id, "start_index": 1, "end_index": 2},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["success"] is True

    _, state = await _run_single_tool_flow(
        f"{unique_id}-sh",
        "share",
        ["gdocs_share_document"],
        "gdocs_share_document",
        {"document_id": doc_id, "anyone": True, "role": "reader"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["success"] is True

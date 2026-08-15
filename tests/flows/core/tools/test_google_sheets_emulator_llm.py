"""
LlmNode + MockLLM matrix for sheets_* against Google API emulator.

Мок только MockLLM. Flow/tools/clients/HTTP — реальные (эмулятор).
Live Google: tests/flows/core/tools/test_google_sheets_integration.py (-m network).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from a2a.helpers.proto_helpers import get_message_text

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from core.clients.google_sheets_client import GoogleSheetsClient
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from tests.fixtures.google_api_emulator import GoogleApiEmulatorHandle
from tests.flows.durable_runtime_harness import ensure_workflow_started


@pytest.fixture()
def sheets_client(google_api_emulator: GoogleApiEmulatorHandle) -> GoogleSheetsClient:
    return GoogleSheetsClient(access_token=google_api_emulator.oauth_token)


def _make_state(
    unique_id: str,
    flow_id: str,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> ExecutionState:
    context_id = f"ctx-sheets-emu-llm-{unique_id}"
    return ExecutionState(
        task_id=f"task-sheets-emu-llm-{unique_id}",
        context_id=context_id,
        user_id="u1",
        session_id=f"{flow_id}:{context_id}",
        content="Выполни",
        variables={"google_access_token": google_api_emulator.oauth_token},
    )


def _parse_tool_payload(content: object) -> JsonObject:
    if isinstance(content, dict):
        return require_json_object(content, "sheets.tool_message")
    if isinstance(content, str):
        return require_json_object(json.loads(content), "sheets.tool_message")
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
    payloads: list[JsonObject] = []
    for message in state.messages:
        if not _message_is_tool(message):
            continue
        payloads.append(_parse_tool_payload(_message_text(message)))
    return payloads


async def _run_single_tool_flow(
    unique_id: str,
    flow_suffix: str,
    tool_ids: list[str],
    tool_call_name: str,
    tool_call_args: dict[str, Any],
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> tuple[dict[str, Any], ExecutionState]:
    flow_id = f"sheets_emu_{flow_suffix}_{unique_id}"
    container = get_container()
    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"Sheets emu {flow_suffix}",
        entry="agent",
        nodes={
            "agent": {
                "type": "llm_node",
                "prompt": "Ты агент для Google Sheets.",
                "tools": [{"tool_id": tid} for tid in tool_ids],
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
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
async def test_create_spreadsheet_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> None:
    _ = app
    result, state = await _run_single_tool_flow(
        unique_id,
        "create",
        ["sheets_create_spreadsheet"],
        "sheets_create_spreadsheet",
        {"title": f"Agent Sheets {unique_id}", "sheet_titles": ["Main"]},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert isinstance(payload["spreadsheet_id"], str)


@pytest.mark.asyncio
async def test_get_metadata_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
    sheets_client: GoogleSheetsClient,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Meta {unique_id}")
    result, state = await _run_single_tool_flow(
        unique_id,
        "meta",
        ["sheets_get_metadata"],
        "sheets_get_metadata",
        {"spreadsheet_id": book.spreadsheet_id},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert payload["spreadsheet_id"] == book.spreadsheet_id


@pytest.mark.asyncio
async def test_list_sheets_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
    sheets_client: GoogleSheetsClient,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(
        f"List {unique_id}", sheet_titles=["Alpha", "Beta"]
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        "list",
        ["sheets_list_sheets"],
        "sheets_list_sheets",
        {"spreadsheet_id": book.spreadsheet_id},
        mock_llm_with_queue,
        google_api_emulator,
    )
    titles = _tool_payloads_from_state(state)[0]["titles"]
    assert "Alpha" in titles and "Beta" in titles


@pytest.mark.asyncio
async def test_get_and_batch_get_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
    sheets_client: GoogleSheetsClient,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Get {unique_id}")
    await sheets_client.update_values(
        book.spreadsheet_id, "Sheet1!A1:B1", [["hello", unique_id]]
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        "get",
        ["sheets_get_values"],
        "sheets_get_values",
        {"spreadsheet_id": book.spreadsheet_id, "range": "Sheet1!A1:B1"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["values"] == [["hello", unique_id]]

    result, state = await _run_single_tool_flow(
        f"{unique_id}-bg",
        "bget",
        ["sheets_batch_get_values"],
        "sheets_batch_get_values",
        {
            "spreadsheet_id": book.spreadsheet_id,
            "ranges": ["Sheet1!A1", "Sheet1!B1"],
        },
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert len(_tool_payloads_from_state(state)[0]["value_ranges"]) == 2


@pytest.mark.asyncio
async def test_update_batch_update_append_clear_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
    sheets_client: GoogleSheetsClient,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Write {unique_id}")
    sid = book.spreadsheet_id

    _, state = await _run_single_tool_flow(
        f"{unique_id}-u",
        "upd",
        ["sheets_update_values"],
        "sheets_update_values",
        {
            "spreadsheet_id": sid,
            "range": "Sheet1!A1:B1",
            "values": [["a", "b"]],
            "value_input_option": "RAW",
        },
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["spreadsheet_id"] == sid

    _, state = await _run_single_tool_flow(
        f"{unique_id}-bu",
        "bupd",
        ["sheets_batch_update_values"],
        "sheets_batch_update_values",
        {
            "spreadsheet_id": sid,
            "data": [{"range": "Sheet1!C1", "values": [["c"]]}],
            "value_input_option": "RAW",
        },
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["spreadsheet_id"] == sid

    _, state = await _run_single_tool_flow(
        f"{unique_id}-ap",
        "append",
        ["sheets_append_rows"],
        "sheets_append_rows",
        {
            "spreadsheet_id": sid,
            "range": "Sheet1!A:C",
            "values": [["x", "y", "z"]],
            "value_input_option": "RAW",
        },
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["spreadsheet_id"] == sid

    _, state = await _run_single_tool_flow(
        f"{unique_id}-cl",
        "clear",
        ["sheets_clear_values"],
        "sheets_clear_values",
        {"spreadsheet_id": sid, "range": "Sheet1!A1"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["spreadsheet_id"] == sid

    _, state = await _run_single_tool_flow(
        f"{unique_id}-bc",
        "bclear",
        ["sheets_batch_clear_values"],
        "sheets_batch_clear_values",
        {"spreadsheet_id": sid, "ranges": ["Sheet1!B1", "Sheet1!C1"]},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["spreadsheet_id"] == sid


@pytest.mark.asyncio
async def test_share_and_structure_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    google_api_emulator: GoogleApiEmulatorHandle,
    sheets_client: GoogleSheetsClient,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Struct {unique_id}")
    sid = book.spreadsheet_id

    _, state = await _run_single_tool_flow(
        f"{unique_id}-sh",
        "share",
        ["sheets_share"],
        "sheets_share",
        {"spreadsheet_id": sid, "anyone": True, "role": "reader"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["anyone"] is True

    _, state = await _run_single_tool_flow(
        f"{unique_id}-se",
        "share_email",
        ["sheets_share"],
        "sheets_share",
        {
            "spreadsheet_id": sid,
            "email": "peer@example.com",
            "role": "writer",
            "anyone": False,
        },
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(state)[0]["email"] == "peer@example.com"

    _, add_state = await _run_single_tool_flow(
        f"{unique_id}-add",
        "add",
        ["sheets_add_sheet"],
        "sheets_add_sheet",
        {"spreadsheet_id": sid, "title": f"Tab-{unique_id}"},
        mock_llm_with_queue,
        google_api_emulator,
    )
    sheet_id = _tool_payloads_from_state(add_state)[0]["sheet_id"]
    assert isinstance(sheet_id, int)

    _, rename_state = await _run_single_tool_flow(
        f"{unique_id}-ren",
        "ren",
        ["sheets_rename_sheet"],
        "sheets_rename_sheet",
        {
            "spreadsheet_id": sid,
            "sheet_id": sheet_id,
            "title": f"Renamed-{unique_id}",
        },
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(rename_state)[0]["title"] == f"Renamed-{unique_id}"

    _, delete_state = await _run_single_tool_flow(
        f"{unique_id}-del",
        "del",
        ["sheets_delete_sheet"],
        "sheets_delete_sheet",
        {"spreadsheet_id": sid, "sheet_id": sheet_id},
        mock_llm_with_queue,
        google_api_emulator,
    )
    assert _tool_payloads_from_state(delete_state)[0]["sheet_id"] == sheet_id

"""
Интеграция Google Sheets: каждый sheets_* тул через LlmNode + MockLLM.

Канон testing.mdc: мок только LLM. Flow, ToolRegistry, Google Sheets API — реальные.
Без monkeypatch HTTP-клиента.

Требует:
  - google_service_account.json
  - GOOGLE_IMPERSONATE_EMAIL (domain-wide delegation)

Запуск:
  GOOGLE_IMPERSONATE_EMAIL=user@domain \\
    uv run pytest tests/flows/core/tools/test_google_sheets_integration.py -m network -v -s
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from a2a.helpers.proto_helpers import get_message_text

from apps.flows.src.models import FlowConfig
from apps.flows.src.state import ExecutionState
from apps.flows.tools.google_sheets.google_sheets import (
    sheets_add_sheet,
    sheets_append_rows,
    sheets_batch_clear_values,
    sheets_batch_get_values,
    sheets_batch_update_values,
    sheets_clear_values,
    sheets_create_spreadsheet,
    sheets_delete_sheet,
    sheets_get_metadata,
    sheets_get_values,
    sheets_list_sheets,
    sheets_rename_sheet,
    sheets_share,
    sheets_update_values,
)
from core.clients.google_sheets_client import GoogleSheetsClient
from core.types import JsonObject, require_json_object
from tests.fixtures.google_sheets_live import (
    google_sheets_service_account_client_email,
    make_google_sheets_client,
    require_google_sheets_live_credentials,
    sheets_execution_variables,
)
from tests.flows.durable_runtime_harness import ensure_workflow_started

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]

_ALL_SHEETS_TOOLS = [
    sheets_create_spreadsheet,
    sheets_get_metadata,
    sheets_list_sheets,
    sheets_get_values,
    sheets_batch_get_values,
    sheets_update_values,
    sheets_batch_update_values,
    sheets_append_rows,
    sheets_clear_values,
    sheets_batch_clear_values,
    sheets_share,
    sheets_add_sheet,
    sheets_rename_sheet,
    sheets_delete_sheet,
]


@pytest.fixture(autouse=True)
def _require_live_sheets() -> None:
    require_google_sheets_live_credentials()


@pytest.fixture()
def sheets_client() -> GoogleSheetsClient:
    return make_google_sheets_client()


def _make_state(unique_id: str, flow_id: str) -> ExecutionState:
    context_id = f"ctx-sheets-{unique_id}"
    return ExecutionState(
        task_id=f"task-sheets-{unique_id}",
        context_id=context_id,
        user_id="u1",
        session_id=f"{flow_id}:{context_id}",
        content="Выполни",
        variables=sheets_execution_variables(),
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
    di,
) -> tuple[dict[str, Any], ExecutionState]:
    flow_id = f"sheets_{flow_suffix}_{unique_id}"

    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"Sheets {flow_suffix}",
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
    await FlowConfig.create_version(flow_config)

    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": tool_call_name, "args": tool_call_args},
            {"type": "text", "content": "Готово."},
        ]
    )

    flow = await di.flow_factory.get_flow(flow_id, tool_registry=di.tool_registry)
    state = _make_state(unique_id, flow_id)
    await ensure_workflow_started(
        di=di,
        state=state,
        flow_id=flow_id,
        branch_id=state.branch_id,
    )
    final_state = await flow.run(state)

    await FlowConfig.delete_by_flow_id(flow_id)
    return final_state, final_state


def test_all_sheets_tools_are_registered_in_suite() -> None:
    names = {tool.name for tool in _ALL_SHEETS_TOOLS}
    assert names == {
        "sheets_create_spreadsheet",
        "sheets_get_metadata",
        "sheets_list_sheets",
        "sheets_get_values",
        "sheets_batch_get_values",
        "sheets_update_values",
        "sheets_batch_update_values",
        "sheets_append_rows",
        "sheets_clear_values",
        "sheets_batch_clear_values",
        "sheets_share",
        "sheets_add_sheet",
        "sheets_rename_sheet",
        "sheets_delete_sheet",
    }


@pytest.mark.asyncio
async def test_create_spreadsheet_via_llm_node(
    app: object, unique_id: str, mock_llm_with_queue: Any, di
) -> None:
    _ = app
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="create",
        tool_ids=["sheets_create_spreadsheet"],
        tool_call_name="sheets_create_spreadsheet",
        tool_call_args={
            "title": f"Agent Sheets {unique_id}",
            "sheet_titles": ["Main"],
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payloads = _tool_payloads_from_state(state)
    assert len(payloads) == 1
    assert isinstance(payloads[0]["spreadsheet_id"], str)
    assert isinstance(payloads[0]["spreadsheet_id"], str)
    assert payloads[0]["spreadsheet_id"] != ""


@pytest.mark.asyncio
async def test_get_metadata_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Meta Target {unique_id}")
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="meta",
        tool_ids=["sheets_get_metadata"],
        tool_call_name="sheets_get_metadata",
        tool_call_args={"spreadsheet_id": book.spreadsheet_id},
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert payload["spreadsheet_id"] == book.spreadsheet_id
    assert payload["title"] == book.title


@pytest.mark.asyncio
async def test_list_sheets_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(
        f"List Target {unique_id}",
        sheet_titles=["Alpha", "Beta"],
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="list",
        tool_ids=["sheets_list_sheets"],
        tool_call_name="sheets_list_sheets",
        tool_call_args={"spreadsheet_id": book.spreadsheet_id},
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    titles = payload["titles"]
    assert isinstance(titles, list)
    assert "Alpha" in titles
    assert "Beta" in titles


@pytest.mark.asyncio
async def test_get_values_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Get Target {unique_id}")
    await sheets_client.update_values(
        book.spreadsheet_id,
        "Sheet1!A1:B1",
        [["hello", unique_id]],
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="get",
        tool_ids=["sheets_get_values"],
        tool_call_name="sheets_get_values",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "range": "Sheet1!A1:B1",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert payload["values"] == [["hello", unique_id]]


@pytest.mark.asyncio
async def test_batch_get_values_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"BatchGet {unique_id}")
    await sheets_client.update_values(
        book.spreadsheet_id,
        "Sheet1!A1:B1",
        [["x", "y"]],
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="bget",
        tool_ids=["sheets_batch_get_values"],
        tool_call_name="sheets_batch_get_values",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "ranges": ["Sheet1!A1", "Sheet1!B1"],
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    ranges = payload["value_ranges"]
    assert isinstance(ranges, list)
    assert len(ranges) == 2


@pytest.mark.asyncio
async def test_update_values_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Update Target {unique_id}")
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="upd",
        tool_ids=["sheets_update_values"],
        tool_call_name="sheets_update_values",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "range": "Sheet1!A1:B1",
            "values": [["from-agent", 7]],
            "value_input_option": "USER_ENTERED",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    _ = _tool_payloads_from_state(state)[0]
    read_back = await sheets_client.get_values(book.spreadsheet_id, "Sheet1!A1:B1")
    assert read_back.values[0][0] == "from-agent"


@pytest.mark.asyncio
async def test_batch_update_values_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"BatchUpd {unique_id}")
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="bupd",
        tool_ids=["sheets_batch_update_values"],
        tool_call_name="sheets_batch_update_values",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "data": [
                {"range": "Sheet1!A1", "values": [["a"]]},
                {"range": "Sheet1!B1", "values": [["b"]]},
            ],
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    _ = _tool_payloads_from_state(state)[0]
    read_back = await sheets_client.get_values(book.spreadsheet_id, "Sheet1!A1:B1")
    assert read_back.values[0] == ["a", "b"]


@pytest.mark.asyncio
async def test_append_rows_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Append Target {unique_id}")
    await sheets_client.update_values(
        book.spreadsheet_id, "Sheet1!A1:B1", [["h1", "h2"]]
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="append",
        tool_ids=["sheets_append_rows"],
        tool_call_name="sheets_append_rows",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "range": "Sheet1!A:B",
            "values": [["row2", unique_id]],
            "insert_data_option": "INSERT_ROWS",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    _ = _tool_payloads_from_state(state)[0]
    read_back = await sheets_client.get_values(book.spreadsheet_id, "Sheet1!A1:B3")
    assert any(unique_id in [str(cell) for cell in row] for row in read_back.values)


@pytest.mark.asyncio
async def test_clear_values_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Clear Target {unique_id}")
    await sheets_client.update_values(
        book.spreadsheet_id, "Sheet1!A1", [["wipe-me"]]
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="clear",
        tool_ids=["sheets_clear_values"],
        tool_call_name="sheets_clear_values",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "range": "Sheet1!A1",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    _ = _tool_payloads_from_state(state)[0]
    read_back = await sheets_client.get_values(book.spreadsheet_id, "Sheet1!A1")
    assert read_back.values == []


@pytest.mark.asyncio
async def test_batch_clear_values_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"BClear {unique_id}")
    await sheets_client.update_values(
        book.spreadsheet_id, "Sheet1!A1:B1", [["1", "2"]]
    )
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="bclear",
        tool_ids=["sheets_batch_clear_values"],
        tool_call_name="sheets_batch_clear_values",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "ranges": ["Sheet1!A1", "Sheet1!B1"],
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    _ = _tool_payloads_from_state(state)[0]
    read_back = await sheets_client.get_values(book.spreadsheet_id, "Sheet1!A1:B1")
    assert read_back.values == []


@pytest.mark.asyncio
async def test_share_anyone_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Share Target {unique_id}")
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="share",
        tool_ids=["sheets_share"],
        tool_call_name="sheets_share",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "anyone": True,
            "role": "reader",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert payload["anyone"] is True


@pytest.mark.asyncio
async def test_share_email_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"ShareEmail {unique_id}")
    email = google_sheets_service_account_client_email()
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="share_email",
        tool_ids=["sheets_share"],
        tool_call_name="sheets_share",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "email": email,
            "role": "writer",
            "anyone": False,
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert payload["email"] == email
    assert payload["anyone"] is False


@pytest.mark.asyncio
async def test_add_rename_delete_sheet_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    sheets_client: GoogleSheetsClient,
    di,
) -> None:
    _ = app
    book = await sheets_client.create_spreadsheet(f"Tabs Target {unique_id}")

    add_result, add_state = await _run_single_tool_flow(
        f"{unique_id}-add",
        flow_suffix="add",
        tool_ids=["sheets_add_sheet"],
        tool_call_name="sheets_add_sheet",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "title": f"Tab-{unique_id}",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert add_result["response"] == "Готово."
    add_payload = _tool_payloads_from_state(add_state)[0]
    sheet_id = add_payload["sheet_id"]
    assert isinstance(sheet_id, int)

    rename_result, rename_state = await _run_single_tool_flow(
        f"{unique_id}-ren",
        flow_suffix="ren",
        tool_ids=["sheets_rename_sheet"],
        tool_call_name="sheets_rename_sheet",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "sheet_id": sheet_id,
            "title": f"Renamed-{unique_id}",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert rename_result["response"] == "Готово."
    rename_payload = _tool_payloads_from_state(rename_state)[0]
    assert rename_payload["title"] == f"Renamed-{unique_id}"

    delete_result, delete_state = await _run_single_tool_flow(
        f"{unique_id}-del",
        flow_suffix="del",
        tool_ids=["sheets_delete_sheet"],
        tool_call_name="sheets_delete_sheet",
        tool_call_args={
            "spreadsheet_id": book.spreadsheet_id,
            "sheet_id": sheet_id,
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert delete_result["response"] == "Готово."
    delete_payload = _tool_payloads_from_state(delete_state)[0]
    assert delete_payload["sheet_id"] == sheet_id
    listed = await sheets_client.list_sheets(book.spreadsheet_id)
    assert f"Renamed-{unique_id}" not in listed.titles


@pytest.mark.asyncio
async def test_create_then_update_then_get_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    di,
) -> None:
    """Цепочка через llm_node: create → update → get (реальный Google)."""
    _ = app
    create_result, create_state = await _run_single_tool_flow(
        f"{unique_id}-c",
        flow_suffix="chain_create",
        tool_ids=["sheets_create_spreadsheet"],
        tool_call_name="sheets_create_spreadsheet",
        tool_call_args={
            "title": f"Chain {unique_id}",
            "sheet_titles": ["Main"],
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert create_result["response"] == "Готово."
    spreadsheet_id = _tool_payloads_from_state(create_state)[0]["spreadsheet_id"]
    assert isinstance(spreadsheet_id, str)
    assert spreadsheet_id != ""

    update_result, update_state = await _run_single_tool_flow(
        f"{unique_id}-u",
        flow_suffix="chain_upd",
        tool_ids=["sheets_update_values"],
        tool_call_name="sheets_update_values",
        tool_call_args={
            "spreadsheet_id": spreadsheet_id,
            "range": "Main!A1:B1",
            "values": [["chain", unique_id]],
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert update_result["response"] == "Готово."

    get_result, get_state = await _run_single_tool_flow(
        f"{unique_id}-g",
        flow_suffix="chain_get",
        tool_ids=["sheets_get_values"],
        tool_call_name="sheets_get_values",
        tool_call_args={
            "spreadsheet_id": spreadsheet_id,
            "range": "Main!A1:B1",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert get_result["response"] == "Готово."
    get_payload = _tool_payloads_from_state(get_state)[0]
    assert get_payload["values"] == [["chain", unique_id]]

"""
sheets_* tools via tool.run against Google API emulator.

Real tools + resolve + client HTTP; credentials from state.variables.
"""

from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.services.google_workspace_client import GoogleWorkspaceClient
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
from core.types import JsonObject, require_json_object
from tests.fixtures.google_api_emulator import GoogleApiEmulatorHandle

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


def _make_state(
    unique_id: str,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-sheets-emu-{unique_id}",
        context_id=f"ctx-sheets-emu-{unique_id}",
        user_id="u1",
        session_id=f"flow-sheets-emu:{unique_id}",
        variables={"google_access_token": google_api_emulator.oauth_token},
    )


def _as_payload(raw: object) -> JsonObject:
    return require_json_object(raw, "sheets.emulator.tool_result")


def test_all_sheets_tools_registered() -> None:
    assert {tool.name for tool in _ALL_SHEETS_TOOLS} == {
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
async def test_all_sheets_tools_via_run(
    google_api_emulator: GoogleApiEmulatorHandle,
    unique_id: str,
    di: FlowsDi,
) -> None:
    state = _make_state(unique_id, google_api_emulator)
    client = GoogleWorkspaceClient(
        oauth_service=di.oauth_service,
        company_credentials=di.company_integration_credential_service,
    )

    def _bound(tool: object) -> object:
        return tool.with_dependencies([client])  # type: ignore[attr-defined]

    created = _as_payload(
        await _bound(sheets_create_spreadsheet).run(
            {"title": f"tool-sheet-{unique_id}", "sheet_titles": ["Main"]},
            state,
        )
    )
    sid = created["spreadsheet_id"]
    assert isinstance(sid, str)

    meta = _as_payload(await _bound(sheets_get_metadata).run({"spreadsheet_id": sid}, state))
    assert meta["title"] == f"tool-sheet-{unique_id}"

    listed = _as_payload(await _bound(sheets_list_sheets).run({"spreadsheet_id": sid}, state))
    assert "Main" in listed["titles"]

    _ = _as_payload(
        await _bound(sheets_update_values).run(
            {
                "spreadsheet_id": sid,
                "range": "Main!A1:B1",
                "values": [["hello", unique_id]],
                "value_input_option": "RAW",
            },
            state,
        )
    )

    got = _as_payload(
        await _bound(sheets_get_values).run(
            {"spreadsheet_id": sid, "range": "Main!A1:B1"},
            state,
        )
    )
    assert got["values"] == [["hello", unique_id]]

    batch_got = _as_payload(
        await _bound(sheets_batch_get_values).run(
            {"spreadsheet_id": sid, "ranges": ["Main!A1", "Main!B1"]},
            state,
        )
    )
    assert len(batch_got["value_ranges"]) == 2

    _ = _as_payload(
        await _bound(sheets_batch_update_values).run(
            {
                "spreadsheet_id": sid,
                "data": [
                    {"range": "Main!C1", "values": [["c"]]},
                ],
                "value_input_option": "RAW",
            },
            state,
        )
    )

    _ = _as_payload(
        await _bound(sheets_append_rows).run(
            {
                "spreadsheet_id": sid,
                "range": "Main!A:C",
                "values": [["r2", "s2", "t2"]],
                "value_input_option": "RAW",
            },
            state,
        )
    )

    _ = _as_payload(
        await _bound(sheets_clear_values).run(
            {"spreadsheet_id": sid, "range": "Main!A1:B1"},
            state,
        )
    )

    _ = _as_payload(
        await _bound(sheets_batch_clear_values).run(
            {"spreadsheet_id": sid, "ranges": ["Main!C1"]},
            state,
        )
    )

    _ = _as_payload(
        await _bound(sheets_share).run(
            {"spreadsheet_id": sid, "email": "share@example.com", "role": "reader"},
            state,
        )
    )

    added = _as_payload(
        await _bound(sheets_add_sheet).run({"spreadsheet_id": sid, "title": "Tab2"}, state)
    )
    sheet_id = added["sheet_id"]
    assert isinstance(sheet_id, int)

    _ = _as_payload(
        await _bound(sheets_rename_sheet).run(
            {"spreadsheet_id": sid, "sheet_id": sheet_id, "title": "Tab2b"},
            state,
        )
    )

    _ = _as_payload(
        await _bound(sheets_delete_sheet).run(
            {"spreadsheet_id": sid, "sheet_id": sheet_id},
            state,
        )
    )

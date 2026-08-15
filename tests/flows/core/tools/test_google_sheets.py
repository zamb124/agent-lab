"""Google Sheets tools: OAuth interrupt when credentials are missing."""

import uuid

import pytest

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.base import ToolArguments
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.tools.google_sheets import (
    sheets_append_rows,
    sheets_create_spreadsheet,
    sheets_get_values,
    sheets_share,
)
from core.state import ExecutionState
from core.state.interrupt import InterruptKind, OAuthInterrupt


def _make_state() -> ExecutionState:
    uid = uuid.uuid4().hex[:12]
    return ExecutionState(
        task_id=f"test-task-{uid}",
        context_id=f"test-context-{uid}",
        user_id="test_user",
        session_id=f"test-sheets:test-context-{uid}",
    )


async def _assert_requires_sheets_oauth(tool: FunctionTool, args: ToolArguments) -> None:
    state = _make_state()
    with pytest.raises(FlowInterrupt) as exc_info:
        _ = await tool.run(args, state)
    interrupt = exc_info.value.body
    assert interrupt.kind == InterruptKind.OAUTH_REQUIRED
    assert isinstance(interrupt, OAuthInterrupt)
    assert interrupt.provider == "google"
    assert interrupt.service == "workspace"


class TestSheetsCreateSpreadsheet:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(self) -> None:
        await _assert_requires_sheets_oauth(
            sheets_create_spreadsheet, {"title": "Leads"}
        )


class TestSheetsGetValues:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(self) -> None:
        await _assert_requires_sheets_oauth(
            sheets_get_values,
            {"spreadsheet_id": "sheet123", "range": "Sheet1!A1:B2"},
        )


class TestSheetsAppendRows:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(self) -> None:
        await _assert_requires_sheets_oauth(
            sheets_append_rows,
            {
                "spreadsheet_id": "sheet123",
                "range": "Sheet1!A:Z",
                "values": [["a", "b"]],
            },
        )


class TestSheetsShare:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(self) -> None:
        await _assert_requires_sheets_oauth(
            sheets_share,
            {"spreadsheet_id": "sheet123", "email": "u@example.com"},
        )

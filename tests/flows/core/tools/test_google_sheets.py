"""Google Sheets tools: OAuth interrupt when credentials are missing."""

import uuid
from unittest.mock import AsyncMock

import pytest

from apps.flows.src.clients.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.base import ToolArguments
from apps.flows.src.tools.decorator import FunctionTool
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from apps.flows.tools.google_sheets.google_sheets import (
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


def _workspace_client_without_credentials() -> GoogleWorkspaceClient:
    oauth = AsyncMock()
    oauth.get_valid_token.return_value = None
    oauth.build_auth_url.return_value = "https://accounts.google.com/o/oauth2/auth"
    company_credentials = AsyncMock()
    company_credentials.get_google_workspace_auth_material.return_value = None
    return GoogleWorkspaceClient(
        oauth_service=oauth,
        company_credentials=company_credentials,
    )


async def _assert_requires_sheets_oauth(tool: FunctionTool, args: ToolArguments) -> None:
    state = _make_state()
    bound = tool.with_dependencies([_workspace_client_without_credentials()])
    token = set_context(
        Context(
            user=User(user_id=state.user_id, name="Test"),
            active_company=Company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        with pytest.raises(FlowInterrupt) as exc_info:
            _ = await bound.run(args, state)
    finally:
        reset_context(token)
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

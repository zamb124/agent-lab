"""Google Sheets tools: OAuth interrupt when credentials are missing."""

import uuid

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.tools.base import ToolArguments
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.tools.google_sheets.google_sheets import (
    sheets_append_rows,
    sheets_create_spreadsheet,
    sheets_get_values,
    sheets_share,
)
from core.config import get_settings
from core.config.models import AuthConfig, AuthProviderConfig
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


def _workspace_client(di: FlowsDi) -> GoogleWorkspaceClient:
    return GoogleWorkspaceClient(
        oauth_service=di.oauth_service,
        company_credentials=di.company_integration_credential_service,
    )


def _enable_google_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "auth",
        AuthConfig(
            jwt_secret_key="test-secret-key-32-bytes-minimum-!",
            providers={
                "google": AuthProviderConfig(
                    client_id="cid",
                    client_secret="csec",
                    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                    token_url="https://oauth2.googleapis.com/token",
                ),
            },
        ),
    )


async def _assert_requires_sheets_oauth(
    di: FlowsDi,
    tool: FunctionTool,
    args: ToolArguments,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_google_oauth(monkeypatch)
    state = _make_state()
    bound = tool.with_dependencies([_workspace_client(di)])
    with pytest.raises(FlowInterrupt) as exc_info:
        _ = await bound.run(args, state)
    interrupt = exc_info.value.body
    assert interrupt.kind == InterruptKind.OAUTH_REQUIRED
    assert isinstance(interrupt, OAuthInterrupt)
    assert interrupt.provider == "google"
    assert interrupt.service == "workspace"


class TestSheetsCreateSpreadsheet:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_sheets_oauth(
            di, sheets_create_spreadsheet, {"title": "Leads"}, monkeypatch
        )


class TestSheetsGetValues:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_sheets_oauth(
            di,
            sheets_get_values,
            {"spreadsheet_id": "sheet123", "range": "Sheet1!A1:B2"},
            monkeypatch,
        )


class TestSheetsAppendRows:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_sheets_oauth(
            di,
            sheets_append_rows,
            {
                "spreadsheet_id": "sheet123",
                "range": "Sheet1!A:Z",
                "values": [["a", "b"]],
            },
            monkeypatch,
        )


class TestSheetsShare:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_sheets_oauth(
            di,
            sheets_share,
            {"spreadsheet_id": "sheet123", "email": "u@example.com"},
            monkeypatch,
        )

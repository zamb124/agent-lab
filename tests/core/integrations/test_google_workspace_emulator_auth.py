"""
Google Workspace auth resolver + company credential API hitting the API emulator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from apps.flows.src.container import get_container
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.platform_facades import resolve_google_workspace_auth
from core.clients.google_sheets_client import GoogleSheetsClient
from core.clients.google_workspace_auth import GoogleAuthMaterial
from core.config import get_settings
from core.config.models import AuthConfig, AuthProviderConfig
from core.context import clear_context, set_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.integrations.company_credentials import (
    CompanyIntegrationCredentialService,
    GoogleWorkspaceCompanyCredentialPut,
)
from core.integrations.constants import (
    COMPANY_INTEGRATION_USER_ID,
    TOKEN_TYPE_SERVICE_ACCOUNT,
)
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.integrations.repository import IntegrationCredentialRepository
from core.models import Company, Context, User
from core.state import ExecutionState
from core.state.interrupt import InterruptKind, OAuthInterrupt
from tests.fixtures.google_api_emulator import GoogleApiEmulatorHandle


@pytest.fixture()
def credential_repository(app: object) -> IntegrationCredentialRepository:
    _ = app
    return IntegrationCredentialRepository(db_url=get_settings().database.shared_url)


@pytest.fixture()
def company_cred_service(
    credential_repository: IntegrationCredentialRepository,
) -> CompanyIntegrationCredentialService:
    return CompanyIntegrationCredentialService(
        repository=credential_repository,
        google_workspace_config=get_settings().google_workspace,
    )


def _admin_context(company_id: str, user_id: str) -> Context:
    user = User(
        user_id=user_id,
        name="Admin",
        emails=["admin@example.com"],
        companies={company_id: ["admin"]},
        active_company_id=company_id,
    )
    return Context(
        user=user,
        active_company=Company(company_id=company_id, name=company_id),
        channel="test",
        trace_id="trace-gw-emu",
    )


def _make_state(user_id: str) -> ExecutionState:
    return ExecutionState(
        task_id="task-gw-emu",
        context_id="ctx-gw-emu",
        user_id=user_id,
        session_id="flow-gw-emu:ctx-gw-emu",
    )


async def _cleanup_google(
    repository: IntegrationCredentialRepository,
    company_id: str,
    user_id: str,
) -> None:
    for service in ("workspace", "docs", "sheets"):
        await repository.delete_by_user_provider_service(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.GOOGLE,
            service=service,
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


@pytest.mark.asyncio
async def test_variables_token_creates_spreadsheet_on_emulator(
    google_api_emulator: GoogleApiEmulatorHandle,
    unique_id: str,
) -> None:
    material = GoogleAuthMaterial(access_token=google_api_emulator.oauth_token)
    client = GoogleSheetsClient(
        access_token=material.access_token,
        credentials_json=material.credentials_json,
        subject=material.subject,
    )
    created = await client.create_spreadsheet(f"vars-token-{unique_id}")
    assert created.spreadsheet_id.startswith("ss_")


@pytest.mark.asyncio
async def test_variables_sa_creates_spreadsheet_on_emulator(
    google_api_emulator: GoogleApiEmulatorHandle,
    unique_id: str,
) -> None:
    client = GoogleSheetsClient(
        credentials_json=google_api_emulator.service_account_json(),
        subject="user@example.com",
    )
    created = await client.create_spreadsheet(f"vars-sa-{unique_id}")
    assert created.spreadsheet_id.startswith("ss_")


@pytest.mark.asyncio
async def test_resolve_user_workspace_then_create(
    google_api_emulator: GoogleApiEmulatorHandle,
    credential_repository: IntegrationCredentialRepository,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = f"co-ws-{unique_id}"
    user_id = f"user-ws-{unique_id}"
    await _cleanup_google(credential_repository, company_id, user_id)
    _enable_google_oauth(monkeypatch)
    _ = get_container()
    now = datetime.now(timezone.utc)
    await credential_repository.upsert(
        IntegrationCredential(
            credential_id=f"cred-ws-{unique_id}",
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.GOOGLE,
            service="workspace",
            access_token=google_api_emulator.oauth_token,
            refresh_token="refresh",
            expires_at=now + timedelta(hours=1),
            scope="https://www.googleapis.com/auth/spreadsheets",
            token_type="Bearer",
            metadata={},
            created_at=now,
            updated_at=now,
        )
    )
    set_context(_admin_context(company_id, user_id))
    try:
        material = await resolve_google_workspace_auth(_make_state(user_id))
        assert material.access_token == google_api_emulator.oauth_token
        client = GoogleSheetsClient(access_token=material.access_token)
        created = await client.create_spreadsheet(f"ws-cred-{unique_id}")
        assert created.spreadsheet_id.startswith("ss_")
    finally:
        clear_context()
        await _cleanup_google(credential_repository, company_id, user_id)


@pytest.mark.asyncio
async def test_resolve_prior_docs_then_create(
    google_api_emulator: GoogleApiEmulatorHandle,
    credential_repository: IntegrationCredentialRepository,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = f"co-docs-{unique_id}"
    user_id = f"user-docs-{unique_id}"
    await _cleanup_google(credential_repository, company_id, user_id)
    _enable_google_oauth(monkeypatch)
    _ = get_container()
    now = datetime.now(timezone.utc)
    await credential_repository.upsert(
        IntegrationCredential(
            credential_id=f"cred-docs-{unique_id}",
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token=google_api_emulator.oauth_token,
            refresh_token="refresh",
            expires_at=now + timedelta(hours=1),
            scope="https://www.googleapis.com/auth/documents",
            token_type="Bearer",
            metadata={},
            created_at=now,
            updated_at=now,
        )
    )
    set_context(_admin_context(company_id, user_id))
    try:
        material = await resolve_google_workspace_auth(_make_state(user_id))
        assert material.access_token == google_api_emulator.oauth_token
        client = GoogleSheetsClient(access_token=material.access_token)
        created = await client.create_spreadsheet(f"docs-prior-{unique_id}")
        assert created.spreadsheet_id.startswith("ss_")
    finally:
        clear_context()
        await _cleanup_google(credential_repository, company_id, user_id)


@pytest.mark.asyncio
async def test_resolve_company_sa_then_create(
    google_api_emulator: GoogleApiEmulatorHandle,
    credential_repository: IntegrationCredentialRepository,
    company_cred_service: CompanyIntegrationCredentialService,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = f"co-sa-{unique_id}"
    user_id = f"user-sa-{unique_id}"
    await _cleanup_google(credential_repository, company_id, user_id)
    await _cleanup_google(
        credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
    )
    _enable_google_oauth(monkeypatch)
    _ = get_container()
    set_context(_admin_context(company_id, user_id))
    try:
        _ = await company_cred_service.upsert_google_workspace_service_account(
            company_id,
            GoogleWorkspaceCompanyCredentialPut(
                service_account_json=google_api_emulator.service_account_json(),
                impersonate_email="user@example.com",
            ),
        )
        material = await resolve_google_workspace_auth(_make_state(user_id))
        assert material.credentials_json is not None
        assert material.subject == "user@example.com"
        assert material.access_token is None
        client = GoogleSheetsClient(
            credentials_json=material.credentials_json,
            subject=material.subject,
        )
        created = await client.create_spreadsheet(f"company-sa-{unique_id}")
        assert created.spreadsheet_id.startswith("ss_")
    finally:
        clear_context()
        await _cleanup_google(credential_repository, company_id, user_id)
        await _cleanup_google(
            credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
        )


@pytest.mark.asyncio
async def test_resolve_empty_raises_oauth_interrupt(
    google_api_emulator: GoogleApiEmulatorHandle,
    credential_repository: IntegrationCredentialRepository,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = google_api_emulator
    company_id = f"co-empty-{unique_id}"
    user_id = f"user-empty-{unique_id}"
    await _cleanup_google(credential_repository, company_id, user_id)
    await _cleanup_google(
        credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
    )
    _enable_google_oauth(monkeypatch)
    _ = get_container()
    set_context(_admin_context(company_id, user_id))
    try:
        with pytest.raises(FlowInterrupt) as exc_info:
            _ = await resolve_google_workspace_auth(_make_state(user_id))
        body = exc_info.value.body
        assert body.kind == InterruptKind.OAUTH_REQUIRED
        assert isinstance(body, OAuthInterrupt)
        assert body.service == "workspace"
        assert body.question == "oauth_required.google.workspace"
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_google_workspace_authorize_returns_url(
    flows_client: httpx.AsyncClient,
    auth_headers_system: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_google_oauth(monkeypatch)
    resp = await flows_client.get(
        "/flows/api/v1/integrations/credentials/google/workspace/authorize",
        headers=auth_headers_system,
        params={"return_path": "/flows"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "authorize_url" in payload
    assert "accounts.google.com" in payload["authorize_url"]
    assert "cid" in payload["authorize_url"]


@pytest.mark.asyncio
async def test_google_workspace_authorize_rejects_bad_return_path(
    flows_client: httpx.AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    resp = await flows_client.get(
        "/flows/api/v1/integrations/credentials/google/workspace/authorize",
        headers=auth_headers_system,
        params={"return_path": "//evil.example"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_company_api_put_get_delete_and_system_put_forbidden(
    flows_client: httpx.AsyncClient,
    auth_headers_system: dict[str, str],
    google_api_emulator: GoogleApiEmulatorHandle,
    credential_repository: IntegrationCredentialRepository,
    unique_id: str,
) -> None:
    put_system = await flows_client.put(
        "/flows/api/v1/integrations/credentials/google/workspace/company",
        headers=auth_headers_system,
        json={
            "service_account_json": google_api_emulator.service_account_json(),
            "impersonate_email": "user@example.com",
        },
    )
    assert put_system.status_code == 403

    get_system = await flows_client.get(
        "/flows/api/v1/integrations/credentials/google/workspace/company",
        headers=auth_headers_system,
    )
    assert get_system.status_code == 200
    assert "configured" in get_system.json()

    company_id = f"co-api-{unique_id}"
    await _cleanup_google(
        credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
    )
    service = CompanyIntegrationCredentialService(
        repository=credential_repository,
        google_workspace_config=get_settings().google_workspace,
    )
    set_context(_admin_context(company_id, f"admin-{unique_id}"))
    try:
        public = await service.upsert_google_workspace_service_account(
            company_id,
            GoogleWorkspaceCompanyCredentialPut(
                service_account_json=google_api_emulator.service_account_json(),
                impersonate_email="user@example.com",
            ),
        )
        assert public.configured is True
        assert public.token_type == TOKEN_TYPE_SERVICE_ACCOUNT
        deleted = await service.delete_google_workspace_service_account(company_id)
        assert deleted is True
    finally:
        clear_context()
        await _cleanup_google(
            credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
        )

    reconcile = await flows_client.post(
        "/flows/api/v1/integrations/google/workspace/system/reconcile",
        headers=auth_headers_system,
    )
    assert reconcile.status_code == 200
    assert reconcile.json()["ensured"] is False
    assert SYSTEM_COMPANY_ID == "system"

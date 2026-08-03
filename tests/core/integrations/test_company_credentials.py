"""
Company-owned integration credentials + Google Workspace auth resolver order.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from apps.flows.src.clients.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.container import get_container
from apps.flows.src.runtime.exceptions import FlowInterrupt
from core.ai.company_settings import decrypt_secret
from core.clients.google_workspace_auth import GoogleAuthMaterial
from core.config.models import (
    GoogleWorkspaceConfig,
    GoogleWorkspaceSystemConfig,
)
from core.context import clear_context, set_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.integrations.company_credentials import (
    CompanyIntegrationConfigError,
    CompanyIntegrationCredentialService,
    CompanyIntegrationPermissionError,
    CompanyIntegrationReadOnlyError,
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

_MINIMAL_SA_JSON = json.dumps(
    {
        "type": "service_account",
        "project_id": "test",
        "private_key_id": "k",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n",
        "client_email": "sa@test.iam.gserviceaccount.com",
        "client_id": "1",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
)


@pytest.fixture()
def credential_repository(app) -> IntegrationCredentialRepository:
    from core.config import get_settings

    return IntegrationCredentialRepository(db_url=get_settings().database.shared_url)


@pytest.fixture()
def company_cred_service(
    credential_repository: IntegrationCredentialRepository,
) -> CompanyIntegrationCredentialService:
    return CompanyIntegrationCredentialService(
        repository=credential_repository,
        google_workspace_config=GoogleWorkspaceConfig(),
    )


def _admin_context(company_id: str, user_id: str = "admin-user") -> Context:
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
        trace_id="trace-company-cred",
    )


def _member_context(company_id: str, user_id: str = "member-user") -> Context:
    user = User(
        user_id=user_id,
        name="Member",
        emails=["member@example.com"],
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    return Context(
        user=user,
        active_company=Company(company_id=company_id, name=company_id),
        channel="test",
        trace_id="trace-member",
    )


def _make_state(user_id: str = "test-user") -> ExecutionState:
    return ExecutionState(
        task_id="task-gw",
        context_id="ctx-gw",
        user_id=user_id,
        session_id="flow-gw:ctx-gw",
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


class TestCompanyGoogleWorkspaceCredential:
    @pytest.mark.asyncio
    async def test_admin_upsert_and_delete(
        self,
        credential_repository: IntegrationCredentialRepository,
        company_cred_service: CompanyIntegrationCredentialService,
        unique_id: str,
    ) -> None:
        company_id = f"co-gw-{unique_id}"
        await _cleanup_google(
            credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
        )
        set_context(_admin_context(company_id))
        try:
            public = await company_cred_service.upsert_google_workspace_service_account(
                company_id,
                GoogleWorkspaceCompanyCredentialPut(
                    service_account_json=_MINIMAL_SA_JSON,
                    impersonate_email="user@example.com",
                ),
            )
            assert public.configured is True
            assert public.impersonate_email == "user@example.com"
            assert public.token_type == TOKEN_TYPE_SERVICE_ACCOUNT

            stored = await credential_repository.get_by_user_provider_service(
                company_id=company_id,
                user_id=COMPANY_INTEGRATION_USER_ID,
                provider=IntegrationProvider.GOOGLE,
                service="workspace",
            )
            assert stored is not None
            assert stored.token_type == TOKEN_TYPE_SERVICE_ACCOUNT
            assert decrypt_secret(stored.access_token) == _MINIMAL_SA_JSON

            material = await company_cred_service.get_google_workspace_auth_material(
                company_id
            )
            assert material is not None
            assert material.credentials_json == _MINIMAL_SA_JSON
            assert material.subject == "user@example.com"

            deleted = await company_cred_service.delete_google_workspace_service_account(
                company_id
            )
            assert deleted is True
            assert (
                await company_cred_service.get_google_workspace_auth_material(company_id)
            ) is None
        finally:
            clear_context()
            await _cleanup_google(
                credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
            )

    @pytest.mark.asyncio
    async def test_member_cannot_upsert(
        self,
        company_cred_service: CompanyIntegrationCredentialService,
        unique_id: str,
    ) -> None:
        company_id = f"co-gw-member-{unique_id}"
        set_context(_member_context(company_id))
        try:
            with pytest.raises(CompanyIntegrationPermissionError):
                await company_cred_service.upsert_google_workspace_service_account(
                    company_id,
                    GoogleWorkspaceCompanyCredentialPut(
                        service_account_json=_MINIMAL_SA_JSON,
                    ),
                )
        finally:
            clear_context()

    @pytest.mark.asyncio
    async def test_system_put_forbidden_without_allow(
        self,
        company_cred_service: CompanyIntegrationCredentialService,
    ) -> None:
        set_context(_admin_context(SYSTEM_COMPANY_ID))
        try:
            with pytest.raises(CompanyIntegrationReadOnlyError):
                await company_cred_service.upsert_google_workspace_service_account(
                    SYSTEM_COMPANY_ID,
                    GoogleWorkspaceCompanyCredentialPut(
                        service_account_json=_MINIMAL_SA_JSON,
                    ),
                )
        finally:
            clear_context()

    @pytest.mark.asyncio
    async def test_reconcile_system_from_config(
        self,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
    ) -> None:
        await _cleanup_google(
            credential_repository, SYSTEM_COMPANY_ID, COMPANY_INTEGRATION_USER_ID
        )
        service = CompanyIntegrationCredentialService(
            repository=credential_repository,
            google_workspace_config=GoogleWorkspaceConfig(
                system=GoogleWorkspaceSystemConfig(
                    enabled=True,
                    service_account_json=_MINIMAL_SA_JSON,
                    impersonate_email="sys@example.com",
                )
            ),
        )
        try:
            result = await service.reconcile_system_google_workspace()
            assert result.ensured is True
            material = await service.get_google_workspace_auth_material(SYSTEM_COMPANY_ID)
            assert material is not None
            assert material.subject == "sys@example.com"
        finally:
            await _cleanup_google(
                credential_repository, SYSTEM_COMPANY_ID, COMPANY_INTEGRATION_USER_ID
            )

    @pytest.mark.asyncio
    async def test_reconcile_disabled_noop(
        self,
        credential_repository: IntegrationCredentialRepository,
    ) -> None:
        service = CompanyIntegrationCredentialService(
            repository=credential_repository,
            google_workspace_config=GoogleWorkspaceConfig(
                system=GoogleWorkspaceSystemConfig(enabled=False)
            ),
        )
        result = await service.reconcile_system_google_workspace()
        assert result.ensured is False

    @pytest.mark.asyncio
    async def test_invalid_sa_json_raises(
        self,
        company_cred_service: CompanyIntegrationCredentialService,
        unique_id: str,
    ) -> None:
        company_id = f"co-gw-bad-{unique_id}"
        set_context(_admin_context(company_id))
        try:
            with pytest.raises(CompanyIntegrationConfigError):
                await company_cred_service.upsert_google_workspace_service_account(
                    company_id,
                    GoogleWorkspaceCompanyCredentialPut(service_account_json="not-json"),
                )
        finally:
            clear_context()


class TestResolveGoogleWorkspaceAuthOrder:
    @pytest.mark.asyncio
    async def test_variables_override_wins(
        self,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from core.config import get_settings
        from core.config.models import AuthConfig, AuthProviderConfig

        company_id = f"co-resolve-{unique_id}"
        user_id = f"user-resolve-{unique_id}"
        await _cleanup_google(credential_repository, company_id, user_id)
        await _cleanup_google(
            credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
        )

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

        _ = get_container()
        set_context(_admin_context(company_id, user_id=user_id))
        try:
            state = _make_state(user_id)
            state.variables = {"google_access_token": "vars-token"}
            material = await GoogleWorkspaceClient().resolve_auth(state)
            assert material == GoogleAuthMaterial(access_token="vars-token")
        finally:
            clear_context()
            await _cleanup_google(credential_repository, company_id, user_id)
            await _cleanup_google(
                credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
            )

    @pytest.mark.asyncio
    async def test_user_workspace_then_prior_then_company_then_interrupt(
        self,
        credential_repository: IntegrationCredentialRepository,
        company_cred_service: CompanyIntegrationCredentialService,
        unique_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from core.config import get_settings
        from core.config.models import AuthConfig, AuthProviderConfig

        company_id = f"co-order-{unique_id}"
        user_id = f"user-order-{unique_id}"
        await _cleanup_google(credential_repository, company_id, user_id)
        await _cleanup_google(
            credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
        )

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

        _ = get_container()
        set_context(_admin_context(company_id, user_id=user_id))
        now = datetime.now(timezone.utc)
        try:
            state = _make_state(user_id)

            with pytest.raises(FlowInterrupt) as exc_info:
                _ = await GoogleWorkspaceClient().resolve_auth(state)
            interrupt = exc_info.value.body
            assert isinstance(interrupt, OAuthInterrupt)
            assert interrupt.kind == InterruptKind.OAUTH_REQUIRED
            assert interrupt.service == "workspace"

            await company_cred_service.upsert_google_workspace_service_account(
                company_id,
                GoogleWorkspaceCompanyCredentialPut(
                    service_account_json=_MINIMAL_SA_JSON,
                    impersonate_email="imp@example.com",
                ),
            )
            company_material = await GoogleWorkspaceClient().resolve_auth(state)
            assert company_material.credentials_json == _MINIMAL_SA_JSON
            assert company_material.subject == "imp@example.com"

            await credential_repository.upsert(
                IntegrationCredential(
                    credential_id=f"prior-{unique_id}",
                    company_id=company_id,
                    user_id=user_id,
                    provider=IntegrationProvider.GOOGLE,
                    service="docs",
                    access_token="prior-docs-token",
                    refresh_token=None,
                    expires_at=now + timedelta(hours=1),
                    created_at=now,
                    updated_at=now,
                )
            )
            prior_material = await GoogleWorkspaceClient().resolve_auth(state)
            assert prior_material.access_token == "prior-docs-token"

            await credential_repository.upsert(
                IntegrationCredential(
                    credential_id=f"ws-{unique_id}",
                    company_id=company_id,
                    user_id=user_id,
                    provider=IntegrationProvider.GOOGLE,
                    service="workspace",
                    access_token="user-workspace-token",
                    refresh_token=None,
                    expires_at=now + timedelta(hours=1),
                    created_at=now,
                    updated_at=now,
                )
            )
            user_material = await GoogleWorkspaceClient().resolve_auth(state)
            assert user_material.access_token == "user-workspace-token"
        finally:
            clear_context()
            await _cleanup_google(credential_repository, company_id, user_id)
            await _cleanup_google(
                credential_repository, company_id, COMPANY_INTEGRATION_USER_ID
            )

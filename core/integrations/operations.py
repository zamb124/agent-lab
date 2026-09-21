"""Credentials интеграций: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from typing import Never

from core.container.base import BaseContainer
from core.context import require_active_company
from core.integrations.company_credentials import (
    CompanyIntegrationConfigError,
    CompanyIntegrationPermissionError,
    CompanyIntegrationReadOnlyError,
    GoogleWorkspaceCompanyCredentialPublic,
    GoogleWorkspaceCompanyCredentialPut,
)
from core.integrations.models import (
    CredentialInfo,
    IntegrationCredentialRefPayload,
    IntegrationDeletedResponse,
    IntegrationProvider,
)
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import EmptyPayload, WsCommandError


def raise_integration(exc: Exception) -> Never:
    if isinstance(exc, CompanyIntegrationPermissionError | CompanyIntegrationReadOnlyError):
        raise WsCommandError("forbidden", str(exc), error_code='forbidden') from exc
    if isinstance(exc, CompanyIntegrationConfigError):
        raise WsCommandError("ws_invalid_payload", str(exc), error_code='ws_invalid_payload') from exc
    raise exc


def _require_ref(payload: IntegrationCredentialRefPayload) -> tuple[IntegrationProvider, str]:
    if payload.provider == "":
        raise WsCommandError("ws_invalid_payload", "provider required", error_code='ws_invalid_payload')
    if payload.service == "":
        raise WsCommandError("ws_invalid_payload", "service required", error_code='ws_invalid_payload')
    try:
        return IntegrationProvider(payload.provider), payload.service
    except ValueError:
        raise WsCommandError(
            "ws_invalid_payload", f"Unknown provider: {payload.provider}",
                  error_code='ws_invalid_payload',
              ) from None


async def op_integrations_credentials_list(
    payload: EmptyPayload,
    *,
    user: User,
    container: BaseContainer,
) -> ListResponse[CredentialInfo]:
    _ = payload
    company_id = require_active_company().company_id
    credentials = await container.integration_credential_repository.list_by_user(
        company_id=company_id,
        user_id=user.user_id,
    )
    return ListResponse[CredentialInfo](
        items=[
            CredentialInfo(
                provider=credential.provider,
                service=credential.service,
                created_at=credential.created_at,
            )
            for credential in credentials
        ]
    )


async def op_integrations_credentials_remove(
    payload: IntegrationCredentialRefPayload,
    *,
    user: User,
    container: BaseContainer,
) -> IntegrationDeletedResponse:
    company_id = require_active_company().company_id
    provider, service = _require_ref(payload)
    deleted = await container.integration_credential_repository.delete_by_user_provider_service(
        company_id=company_id,
        user_id=user.user_id,
        provider=provider,
        service=service,
    )
    if not deleted:
        raise WsCommandError("not_found", "Credential not found", error_code='not_found')
    return IntegrationDeletedResponse(deleted=True)


async def op_integrations_workspace_company_get(
    payload: EmptyPayload,
    *,
    user: User,
    container: BaseContainer,
) -> GoogleWorkspaceCompanyCredentialPublic:
    _ = payload, user
    company_id = require_active_company().company_id
    return (
        await container.company_integration_credential_service.get_google_workspace_company_public(
            company_id
        )
    )


async def op_integrations_workspace_company_put(
    payload: GoogleWorkspaceCompanyCredentialPut,
    *,
    user: User,
    container: BaseContainer,
) -> GoogleWorkspaceCompanyCredentialPublic:
    _ = user
    company_id = require_active_company().company_id
    try:
        return await container.company_integration_credential_service.upsert_google_workspace_service_account(
            company_id,
            payload,
        )
    except (
        CompanyIntegrationPermissionError,
        CompanyIntegrationReadOnlyError,
        CompanyIntegrationConfigError,
    ) as exc:
        raise_integration(exc)


async def op_integrations_workspace_company_delete(
    payload: EmptyPayload,
    *,
    user: User,
    container: BaseContainer,
) -> IntegrationDeletedResponse:
    _ = payload, user
    company_id = require_active_company().company_id
    try:
        deleted = await container.company_integration_credential_service.delete_google_workspace_service_account(
            company_id,
        )
    except (
        CompanyIntegrationPermissionError,
        CompanyIntegrationReadOnlyError,
        CompanyIntegrationConfigError,
    ) as exc:
        raise_integration(exc)
    if not deleted:
        raise WsCommandError("not_found", "Company credential not found", error_code='not_found')
    return IntegrationDeletedResponse(deleted=True)

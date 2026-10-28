"""Credentials интеграций: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from typing import Never

from core.context import require_active_company
from core.di.platform import PlatformDi
from core.integrations.company_credentials import (
    CompanyIntegrationConfigError,
    CompanyIntegrationPermissionError,
    CompanyIntegrationReadOnlyError,
    GoogleWorkspaceCompanyCredentialPublic,
    GoogleWorkspaceCompanyCredentialPut,
)
from core.integrations.models import (
    CredentialInfo,
    IntegrationCredential,
    IntegrationCredentialRefPayload,
    IntegrationDeletedResponse,
    IntegrationProvider,
)
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import EmptyPayload, Operation, WsCommandError


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
    di: PlatformDi,
) -> ListResponse[CredentialInfo]:
    _ = payload, di
    company_id = require_active_company().company_id
    credentials = await IntegrationCredential.list_by_created_at_for_user(
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
    di: PlatformDi,
) -> IntegrationDeletedResponse:
    _ = di
    company_id = require_active_company().company_id
    provider, service = _require_ref(payload)
    deleted = await IntegrationCredential.delete_by_user_provider_service(
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
    di: PlatformDi,
) -> GoogleWorkspaceCompanyCredentialPublic:
    _ = payload, user
    company_id = require_active_company().company_id
    return (
        await di.company_integration_credential_service.get_google_workspace_company_public(
            company_id
        )
    )


async def op_integrations_workspace_company_put(
    payload: GoogleWorkspaceCompanyCredentialPut,
    *,
    user: User,
    di: PlatformDi,
) -> GoogleWorkspaceCompanyCredentialPublic:
    _ = user
    company_id = require_active_company().company_id
    try:
        return await di.company_integration_credential_service.upsert_google_workspace_service_account(
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
    di: PlatformDi,
) -> IntegrationDeletedResponse:
    _ = payload, user
    company_id = require_active_company().company_id
    try:
        deleted = await di.company_integration_credential_service.delete_google_workspace_service_account(
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


INTEGRATIONS_CREDENTIALS_LIST_OPERATION: Operation[EmptyPayload, PlatformDi] = Operation(
    payload_model=EmptyPayload, fn=op_integrations_credentials_list
)
INTEGRATIONS_CREDENTIALS_REMOVE_OPERATION: Operation[IntegrationCredentialRefPayload, PlatformDi] = Operation(
    payload_model=IntegrationCredentialRefPayload, fn=op_integrations_credentials_remove
)
INTEGRATIONS_WORKSPACE_COMPANY_GET_OPERATION: Operation[EmptyPayload, PlatformDi] = Operation(
    payload_model=EmptyPayload, fn=op_integrations_workspace_company_get
)
INTEGRATIONS_WORKSPACE_COMPANY_PUT_OPERATION: Operation[GoogleWorkspaceCompanyCredentialPut, PlatformDi] = Operation(
    payload_model=GoogleWorkspaceCompanyCredentialPut, fn=op_integrations_workspace_company_put
)
INTEGRATIONS_WORKSPACE_COMPANY_DELETE_OPERATION: Operation[EmptyPayload, PlatformDi] = Operation(
    payload_model=EmptyPayload, fn=op_integrations_workspace_company_delete
)

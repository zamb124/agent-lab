"""Google Workspace auth for Docs/Sheets tools."""

from __future__ import annotations

from apps.flows.src.runtime.exceptions import FlowInterrupt
from core.clients.google_workspace_auth import (
    GoogleAuthMaterial,
    auth_material_from_execution_variables,
)
from core.clients.google_workspace_scopes import (
    GOOGLE_OAUTH_SERVICE_CANONICAL,
    GOOGLE_OAUTH_SERVICE_PRIOR_KEYS,
    scopes_for_google_service,
)
from core.context import get_context
from core.integrations.company_credentials import CompanyIntegrationCredentialService
from core.integrations.constants import TOKEN_TYPE_SERVICE_ACCOUNT
from core.integrations.models import IntegrationProvider
from core.integrations.oauth_service import OAuthService
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import OAuthInterrupt
from core.tracing.context import get_current_trace_context
from core.types import JsonObject

logger = get_logger(__name__)


class GoogleWorkspaceClient:
    """Auth material for Google Docs/Sheets tools."""

    _oauth_service: OAuthService
    _company_credentials: CompanyIntegrationCredentialService

    def __init__(
        self,
        *,
        oauth_service: OAuthService,
        company_credentials: CompanyIntegrationCredentialService,
    ) -> None:
        self._oauth_service = oauth_service
        self._company_credentials = company_credentials

    async def resolve_auth(self, state: ExecutionState) -> GoogleAuthMaterial:
        """
        Порядок: state.variables → user service=workspace → prior docs/sheets credentials →
        company user_id=__company__ SA → OAuthInterrupt (Connect Google, service=workspace).
        """
        from_vars = auth_material_from_execution_variables(state.variables)
        if from_vars is not None:
            return from_vars

        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError("Context with an active company is required for Google Workspace auth")

        company_id = ctx.active_company.company_id
        user_id = ctx.user.user_id
        oauth = self._oauth_service

        workspace_cred = await oauth.get_valid_token(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        )
        if workspace_cred is not None and workspace_cred.token_type != TOKEN_TYPE_SERVICE_ACCOUNT:
            logger.debug("flows.google.workspace.user.workspace.credential", user=user_id)
            return GoogleAuthMaterial(access_token=workspace_cred.access_token)

        for prior_service in GOOGLE_OAUTH_SERVICE_PRIOR_KEYS:
            prior_cred = await oauth.get_valid_token(
                company_id=company_id,
                user_id=user_id,
                provider=IntegrationProvider.GOOGLE,
                service=prior_service,
            )
            if prior_cred is not None and prior_cred.token_type != TOKEN_TYPE_SERVICE_ACCOUNT:
                logger.debug("flows.google.workspace.prior.credential.service", service=prior_service, user=user_id)
                return GoogleAuthMaterial(access_token=prior_cred.access_token)

        company_material = await self._company_credentials.get_google_workspace_auth_material(
            company_id
        )
        if company_material is not None:
            logger.debug("flows.google.workspace.company.sa.credential", company=company_id)
            return company_material

        scopes = scopes_for_google_service(GOOGLE_OAUTH_SERVICE_CANONICAL)
        flow_context: JsonObject = {
            "flow_id": state.session_flow_id,
            "session_id": state.session_id,
            "task_id": state.task_id,
            "context_id": state.context_id,
            "branch_id": state.branch_id,
            "channel": "a2a",
            "user_id": user_id,
            "context_data": ctx.model_dump(mode="json"),
        }
        saved_trace_context = get_current_trace_context()
        if saved_trace_context is not None:
            flow_context["trace_context"] = saved_trace_context

        auth_url = await oauth.build_auth_url(
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
            scopes=scopes,
            user_id=user_id,
            company_id=company_id,
            flow_context=flow_context,
        )
        logger.info("flows.google.workspace.credential.raising.oauthinterrupt", user=user_id)
        raise FlowInterrupt(
            body=OAuthInterrupt(
                question="oauth_required.google.workspace",
                auth_url=auth_url,
                provider="google",
                service=GOOGLE_OAUTH_SERVICE_CANONICAL,
            ),
        )

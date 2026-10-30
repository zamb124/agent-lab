"""Live same-context Flow UI share grants and scoped token exchange."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import final

from apps.flows.src.durable_execution import DurableWorkflowRuntime
from apps.flows.src.flow_ui.projection import validate_redacted_paths
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.state import ExecutionState
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.models.flow_ui_share import (
    FlowUIShareCreateRequest,
    FlowUIShareCreateResponse,
    FlowUIShareExchangeResponse,
    FlowUIShareGrant,
)
from core.short_links.service import ShortLinkService
from core.utils.tokens import TokenService

_FLOWS_SERVICE_BASE_URL = "/flows"

_SHARE_TOKEN_MAX_SECONDS = 900


def _session_id(flow_id: str, context_id: str) -> str:
    return f"{flow_id}:{context_id}"


def flow_ui_share_visitor_user_id(grant_id: str) -> str:
    """AuthN id share-посетителя. Без ``:`` — OpenFGA ``user:<id>`` иначе malformed."""
    if not grant_id:
        raise ValueError("grant_id is required for share visitor user_id")
    return f"flow-ui-share-{grant_id}"


def _assert_owner(state: ExecutionState, user_id: str) -> None:
    if user_id not in {state.user_id, state.initiator_user_id}:
        raise PermissionError("Only the Flow UI session owner can manage share grants")


@final
class FlowUIShareService:
    def __init__(
        self,
        *,
        workflow_runtime: DurableWorkflowRuntime,
        short_link_service: ShortLinkService,
        token_service: TokenService,
        flow_access_service: FlowAccessService,
        authz: AuthzService,
    ) -> None:
        self._workflow_runtime = workflow_runtime
        self._short_links = short_link_service
        self._tokens = token_service
        self._flow_access = flow_access_service
        self._authz = authz

    async def create(
        self,
        *,
        request: FlowUIShareCreateRequest,
        company_id: str,
        user_id: str,
        public_host: str,
    ) -> FlowUIShareCreateResponse:
        state = await self._workflow_runtime.get_state(
            _session_id(request.flow_id, request.context_id)
        )
        if state is None:
            raise ValueError("Flow UI session does not exist")
        _assert_owner(state, user_id)
        await self._authz.require_relation(
            AuthzRelation.CAN_SHARE,
            AuthzObject.flow(request.flow_id, company_id=company_id),
            user_id=user_id,
        )
        if state.session_flow_id != request.flow_id or state.context_id != request.context_id:
            raise ValueError("Flow UI share target identity mismatch")

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        grant = FlowUIShareGrant(
            grant_id=secrets.token_urlsafe(32),
            company_id=company_id,
            flow_id=request.flow_id,
            branch_id=state.branch_id,
            context_id=request.context_id,
            permission=request.permission,
            redacted_paths=validate_redacted_paths(list(request.redacted_paths)),
            created_by_user_id=user_id,
            expires_at=expires_at,
            created_at=now,
        )
        _ = await FlowUIShareGrant.set(grant)
        try:
            await self._flow_access.sync_share_created(
                share_grant_id=grant.grant_id,
                flow_id=grant.flow_id,
                company_id=company_id,
                owner_user_id=user_id,
                permission=grant.permission,
            )
            share_url = await self._short_links.mint_flow_ui_session_share(
                grant.grant_id,
                expires_at,
                host=public_host,
            )
        except Exception as exc:
            await self._flow_access.sync_share_revoked(grant.grant_id)
            _ = await FlowUIShareGrant.revoke_by_creator(
                grant_id=grant.grant_id,
                company_id=company_id,
                created_by_user_id=user_id,
            )
            raise exc
        return FlowUIShareCreateResponse(grant=grant, share_url=share_url)

    async def list_for_owner(
        self,
        *,
        company_id: str,
        user_id: str,
        flow_id: str,
        context_id: str,
    ) -> list[FlowUIShareGrant]:
        state = await self._workflow_runtime.get_state(_session_id(flow_id, context_id))
        if state is None:
            raise ValueError("Flow UI session does not exist")
        _assert_owner(state, user_id)
        return await FlowUIShareGrant.list_for_owner_by_created_at_desc(
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
            created_by_user_id=user_id,
        )

    async def revoke(
        self,
        *,
        grant_id: str,
        company_id: str,
        user_id: str,
    ) -> bool:
        revoked = await FlowUIShareGrant.revoke_by_creator(
            grant_id=grant_id,
            company_id=company_id,
            created_by_user_id=user_id,
        )
        if revoked:
            await self._flow_access.sync_share_revoked(grant_id)
        return revoked

    async def authorize(
        self,
        *,
        grant_id: str,
        company_id: str,
        flow_id: str,
        context_id: str,
        require_editor: bool = False,
        user_id: str | None = None,
    ) -> FlowUIShareGrant:
        grant = await FlowUIShareGrant.active_for_grant(grant_id)
        if grant is None:
            raise PermissionError("Flow UI share grant is missing, expired or revoked")
        if (
            grant.company_id != company_id
            or grant.flow_id != flow_id
            or grant.context_id != context_id
        ):
            raise PermissionError("Flow UI share grant scope mismatch")
        if require_editor and grant.permission != "editor":
            raise PermissionError("Flow UI share grant is read-only")
        subject_user_id = user_id if user_id is not None else "share_visitor"
        if require_editor:
            await self._authz.require_can_edit(
                AuthzObject.flow_ui_share(grant.grant_id),
                user_id=subject_user_id,
            )
        else:
            await self._authz.require_can_view(
                AuthzObject.flow_ui_share(grant.grant_id),
                user_id=subject_user_id,
            )
        state = await self._workflow_runtime.get_state(
            _session_id(flow_id, context_id),
            company_id=grant.company_id,
        )
        if state is None:
            raise PermissionError("Shared Flow UI session no longer exists")
        if state.branch_id != grant.branch_id:
            raise PermissionError("Shared Flow UI durable identity no longer matches the grant")
        return grant

    async def exchange(
        self,
        *,
        grant_id: str,
        origin: str,
    ) -> FlowUIShareExchangeResponse:
        grant = await FlowUIShareGrant.active_for_grant(grant_id)
        if grant is None:
            raise PermissionError("Flow UI share grant is missing, expired or revoked")
        _ = await self.authorize(
            grant_id=grant_id,
            company_id=grant.company_id,
            flow_id=grant.flow_id,
            context_id=grant.context_id,
            user_id="share_visitor",
        )
        now = datetime.now(UTC)
        seconds_left = max(1, int((grant.expires_at - now).total_seconds()))
        token_seconds = min(_SHARE_TOKEN_MAX_SECONDS, seconds_left)
        token = self._tokens.create_flow_ui_share_token(
            user_id=flow_ui_share_visitor_user_id(grant.grant_id),
            company_id=grant.company_id,
            expires_in=token_seconds,
            metadata={
                "issued_by": "flow_ui_share_exchange",
                "flow_ui_share_grant_id": grant.grant_id,
                "flow_ui_share_permission": grant.permission,
                "flow_ui_share_flow_id": grant.flow_id,
                "flow_ui_share_branch_id": grant.branch_id,
                "flow_ui_share_context_id": grant.context_id,
                "flow_ui_share_origin": origin,
            },
        )
        return FlowUIShareExchangeResponse(
            token=token,
            expires_at=now + timedelta(seconds=token_seconds),
            flow_id=grant.flow_id,
            branch_id=grant.branch_id,
            context_id=grant.context_id,
            permission=grant.permission,
            redacted_paths=list(grant.redacted_paths),
            flows_base_url=_FLOWS_SERVICE_BASE_URL,
        )


__all__ = ["FlowUIShareService"]

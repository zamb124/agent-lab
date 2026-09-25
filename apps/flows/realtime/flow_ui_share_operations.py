"""Live Flow UI shares: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
from core.models.flow_ui_share import (
    FlowUIShareCreatePayload,
    FlowUIShareCreateResponse,
    FlowUIShareDeletedResponse,
    FlowUIShareGrant,
    FlowUIShareGrantIdPayload,
    FlowUIShareListPayload,
)
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import (
    raise_conflict,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)


async def op_flows_flow_ui_shares_list(
    payload: FlowUIShareListPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[FlowUIShareGrant]:
    scope = await require_company_member(di)
    try:
        items = await di.flow_ui_share_service.list_for_owner(
            company_id=scope.company_id,
            user_id=user.user_id,
            flow_id=payload.flow_id,
            context_id=payload.context_id,
        )
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_not_found(exc)
    return ListResponse[FlowUIShareGrant](items=items)


async def op_flows_flow_ui_shares_create(
    payload: FlowUIShareCreatePayload,
    *,
    user: User,
    di: Di,
) -> FlowUIShareCreateResponse:
    if payload.public_host.strip() == "":
        raise_invalid(ValueError("Host is required"))
    scope = await require_company_member(di)
    try:
        return await di.flow_ui_share_service.create(
            request=payload,
            company_id=scope.company_id,
            user_id=user.user_id,
            public_host=payload.public_host,
        )
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_conflict(exc)


async def op_flows_flow_ui_shares_remove(
    payload: FlowUIShareGrantIdPayload,
    *,
    user: User,
    di: Di,
) -> FlowUIShareDeletedResponse:
    scope = await require_company_member(di)
    revoked = await di.flow_ui_share_service.revoke(
        grant_id=payload.grant_id,
        company_id=scope.company_id,
        user_id=user.user_id,
    )
    if not revoked:
        raise_not_found(LookupError("Flow UI share grant not found"))
    return FlowUIShareDeletedResponse(status="deleted", grant_id=payload.grant_id)

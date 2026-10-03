"""Control plane for live Flow UI grants; screen data still travels over A2A."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request

from apps.flows.di import Di
from apps.flows.realtime.flow_ui_share_operations import (
    op_flows_flow_ui_shares_create,
    op_flows_flow_ui_shares_list,
    op_flows_flow_ui_shares_remove,
)
from core.context import require_context
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.flow_ui_share import (
    FlowUIShareCreatePayload,
    FlowUIShareCreateRequest,
    FlowUIShareCreateResponse,
    FlowUIShareDeletedResponse,
    FlowUIShareExchangeResponse,
    FlowUIShareGrant,
    FlowUIShareGrantIdPayload,
    FlowUIShareListPayload,
)
from core.pagination import ListResponse
from core.websocket import WsCommandError, raise_not_found

router = APIRouter(prefix="/flow-ui/shares", tags=["flow-ui-shares"])


def _exchange_origin(request: Request) -> str:
    raw = (request.headers.get("origin") or "").strip().rstrip("/")
    if not raw:
        raise WsCommandError("ws_invalid_payload", "Origin header is required", error_code="ws_invalid_payload")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        raise WsCommandError("ws_invalid_payload", "Origin header is invalid", error_code="ws_invalid_payload")
    if raw != build_service_base_url(request).rstrip("/"):
        raise WsCommandError("forbidden", "Share token exchange origin mismatch", error_code="forbidden")
    return raw


@router.post("", response_model=FlowUIShareCreateResponse)
async def create_flow_ui_share(
    body: FlowUIShareCreateRequest,
    request: Request,
    di: Di,
) -> FlowUIShareCreateResponse:
    host = request.headers.get("host")
    return await op_flows_flow_ui_shares_create(
        FlowUIShareCreatePayload.model_validate(
            {**body.model_dump(), "public_host": host if host is not None else ""}
        ),
        user=require_context().user,
        di=di,
    )


@router.get("", response_model=ListResponse[FlowUIShareGrant])
async def list_flow_ui_shares(
    di: Di,
    flow_id: Annotated[str, Query(min_length=1)],
    context_id: Annotated[str, Query(min_length=1)],
) -> ListResponse[FlowUIShareGrant]:
    return await op_flows_flow_ui_shares_list(
        FlowUIShareListPayload(flow_id=flow_id, context_id=context_id),
        user=require_context().user,
        di=di,
    )


@router.delete("/{grant_id}")
async def revoke_flow_ui_share(
    grant_id: str,
    di: Di,
) -> FlowUIShareDeletedResponse:
    return await op_flows_flow_ui_shares_remove(
        FlowUIShareGrantIdPayload(grant_id=grant_id),
        user=require_context().user,
        di=di,
    )


@router.post("/exchange/{grant_id}", response_model=FlowUIShareExchangeResponse)
async def exchange_flow_ui_share(
    grant_id: str,
    request: Request,
    di: Di,
) -> FlowUIShareExchangeResponse:
    try:
        return await di.flow_ui_share_service.exchange(
            grant_id=grant_id,
            origin=_exchange_origin(request),
        )
    except PermissionError as exc:
        raise_not_found(exc)


__all__ = ["router"]

"""Control plane for live Flow UI grants; screen data still travels over A2A."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request

from apps.flows.realtime.flow_ui_share_operations import (
    op_flows_flow_ui_shares_create,
    op_flows_flow_ui_shares_list,
    op_flows_flow_ui_shares_remove,
)
from apps.flows.src.dependencies import ContainerDep
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

router = APIRouter(prefix="/flow-ui/shares", tags=["flow-ui-shares"])


def _exchange_origin(request: Request) -> str:
    raw = (request.headers.get("origin") or "").strip().rstrip("/")
    if not raw:
        raise HTTPException(status_code=400, detail="Origin header is required")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        raise HTTPException(status_code=400, detail="Origin header is invalid")
    if raw != build_service_base_url(request).rstrip("/"):
        raise HTTPException(status_code=403, detail="Share token exchange origin mismatch")
    return raw


@router.post("", response_model=FlowUIShareCreateResponse)
async def create_flow_ui_share(
    body: FlowUIShareCreateRequest,
    request: Request,
    container: ContainerDep,
) -> FlowUIShareCreateResponse:
    host = request.headers.get("host")
    return await op_flows_flow_ui_shares_create(
        FlowUIShareCreatePayload.model_validate(
            {**body.model_dump(), "public_host": host if host is not None else ""}
        ),
        user=require_context().user,
        container=container,
    )


@router.get("", response_model=ListResponse[FlowUIShareGrant])
async def list_flow_ui_shares(
    container: ContainerDep,
    flow_id: Annotated[str, Query(min_length=1)],
    context_id: Annotated[str, Query(min_length=1)],
) -> ListResponse[FlowUIShareGrant]:
    return await op_flows_flow_ui_shares_list(
        FlowUIShareListPayload(flow_id=flow_id, context_id=context_id),
        user=require_context().user,
        container=container,
    )


@router.delete("/{grant_id}")
async def revoke_flow_ui_share(
    grant_id: str,
    container: ContainerDep,
) -> FlowUIShareDeletedResponse:
    return await op_flows_flow_ui_shares_remove(
        FlowUIShareGrantIdPayload(grant_id=grant_id),
        user=require_context().user,
        container=container,
    )


@router.post("/exchange/{grant_id}", response_model=FlowUIShareExchangeResponse)
async def exchange_flow_ui_share(
    grant_id: str,
    request: Request,
    container: ContainerDep,
) -> FlowUIShareExchangeResponse:
    try:
        return await container.flow_ui_share_service.exchange(
            grant_id=grant_id,
            origin=_exchange_origin(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["router"]

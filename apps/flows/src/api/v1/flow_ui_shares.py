"""Control plane for live Flow UI grants; screen data still travels over A2A."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from apps.flows.src.dependencies import ContainerDep
from core.context import require_context
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.flow_ui_share import (
    FlowUIShareCreateRequest,
    FlowUIShareCreateResponse,
    FlowUIShareExchangeResponse,
    FlowUIShareGrant,
)

router = APIRouter(prefix="/flow-ui/shares", tags=["flow-ui-shares"])


def _scope() -> tuple[str, str]:
    context = require_context()
    if context.active_company is None:
        raise HTTPException(status_code=400, detail="Active company is required")
    return context.active_company.company_id, context.user.user_id


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
    company_id, user_id = _scope()
    try:
        return await container.flow_ui_share_service.create(
            request=body,
            company_id=company_id,
            user_id=user_id,
            public_host=request.headers.get("host", ""),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[FlowUIShareGrant])
async def list_flow_ui_shares(
    container: ContainerDep,
    flow_id: Annotated[str, Query(min_length=1)],
    context_id: Annotated[str, Query(min_length=1)],
) -> list[FlowUIShareGrant]:
    company_id, user_id = _scope()
    try:
        return await container.flow_ui_share_service.list_for_owner(
            company_id=company_id,
            user_id=user_id,
            flow_id=flow_id,
            context_id=context_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_flow_ui_share(
    grant_id: str,
    container: ContainerDep,
) -> Response:
    company_id, user_id = _scope()
    revoked = await container.flow_ui_share_service.revoke(
        grant_id=grant_id,
        company_id=company_id,
        user_id=user_id,
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="Flow UI share grant not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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

"""HTTP API фермы code_agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.guest_runtime.di import Di
from apps.guest_runtime.services.identity import guest_identity_scope
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.guest_runtime.models import (
    GuestEnsureLeaseRequest,
    GuestEnsureLeaseResponse,
    GuestRebuildRequest,
    GuestRebuildResponse,
    GuestRuntimeLogsResponse,
    GuestRuntimeStatusResponse,
)
from core.models.identity_models import Company, User
from core.types import JsonObject
from core.websocket import raise_invalid

router = APIRouter(tags=["guest-runtime"])


async def _load_identity(
    *, user_id: str, company_id: str
) -> tuple[User, Company]:
    user = await User.get(user_id)
    if user is None:
        raise PlatformAccessDeniedError(
            f"user not found: {user_id}",
            error_code="user_not_found",
            error_params={"user_id": user_id},
        )
    company = await Company.get(company_id)
    if company is None:
        raise PlatformAccessDeniedError(
            f"company not found: {company_id}",
            error_code="company_not_found",
            error_params={"company_id": company_id},
        )
    return user, company


@router.post("/rebuild", response_model=GuestRebuildResponse)
async def rebuild_guest_image(
    body: GuestRebuildRequest,
    di: Di,
) -> GuestRebuildResponse:
    user, company = await _load_identity(
        user_id=body.user_id, company_id=body.company_id
    )
    async with guest_identity_scope(user=user, company=company):
        try:
            return await di.farm_service.rebuild(body)
        except ValueError as exc:
            raise_invalid(exc)


@router.post("/leases/ensure", response_model=GuestEnsureLeaseResponse)
async def ensure_guest_lease(
    body: GuestEnsureLeaseRequest,
    di: Di,
) -> GuestEnsureLeaseResponse:
    user, company = await _load_identity(
        user_id=body.user_id, company_id=body.company_id
    )
    async with guest_identity_scope(user=user, company=company):
        try:
            return await di.farm_service.ensure_lease(body)
        except ValueError as exc:
            raise_invalid(exc)


@router.get("/runtimes/{flow_id}/{node_id}", response_model=GuestRuntimeStatusResponse)
async def guest_runtime_status(
    flow_id: str,
    node_id: str,
    di: Di,
) -> GuestRuntimeStatusResponse:
    try:
        return await di.farm_service.status(flow_id, node_id)
    except ValueError as exc:
        raise_invalid(exc)


@router.get("/runtimes/{flow_id}/{node_id}/logs", response_model=GuestRuntimeLogsResponse)
async def guest_runtime_logs(
    flow_id: str,
    node_id: str,
    di: Di,
    task_id: Annotated[str | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    context_id: Annotated[str | None, Query()] = None,
) -> GuestRuntimeLogsResponse:
    try:
        return await di.farm_service.logs(
            flow_id,
            node_id,
            task_id=task_id,
            session_id=session_id,
            context_id=context_id,
        )
    except ValueError as exc:
        raise_invalid(exc)


@router.delete("/runtimes/{flow_id}/{node_id}", status_code=204)
async def drop_guest_runtime(
    flow_id: str,
    node_id: str,
    di: Di,
) -> None:
    try:
        await di.farm_service.drop_runtime(flow_id, node_id)
    except ValueError as exc:
        raise_invalid(exc)


@router.post("/a2a/{flow_id}/{node_id}")
async def guest_a2a(
    flow_id: str,
    node_id: str,
    rpc: JsonObject,
    di: Di,
) -> JsonObject:
    lease = await di.farm_service.get_lease(flow_id, node_id)
    if lease is None:
        raise PlatformNotFoundError("guest lease not found", error_code="guest_lease_not_found")
    user, company = await _load_identity(
        user_id=lease.user_id, company_id=lease.company_id
    )
    async with guest_identity_scope(user=user, company=company):
        try:
            return await di.farm_service.invoke_a2a(flow_id, node_id, rpc)
        except ValueError as exc:
            raise_invalid(exc)

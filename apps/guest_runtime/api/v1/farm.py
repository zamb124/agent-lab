"""HTTP API фермы code_agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.guest_runtime.container import GuestRuntimeContainer
from apps.guest_runtime.dependencies import ContainerDep
from apps.guest_runtime.services.identity import guest_identity_scope
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

router = APIRouter(tags=["guest-runtime"])


async def _load_identity(
    container: GuestRuntimeContainer, *, user_id: str, company_id: str
) -> tuple[User, Company]:
    user = await container.user_repository.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail=f"user not found: {user_id}")
    company = await container.company_repository.get(company_id)
    if company is None:
        raise HTTPException(status_code=401, detail=f"company not found: {company_id}")
    return user, company


@router.post("/rebuild", response_model=GuestRebuildResponse)
async def rebuild_guest_image(
    body: GuestRebuildRequest,
    container: ContainerDep,
) -> GuestRebuildResponse:
    user, company = await _load_identity(
        container, user_id=body.user_id, company_id=body.company_id
    )
    async with guest_identity_scope(user=user, company=company):
        return await container.farm_service.rebuild(body)


@router.post("/leases/ensure", response_model=GuestEnsureLeaseResponse)
async def ensure_guest_lease(
    body: GuestEnsureLeaseRequest,
    container: ContainerDep,
) -> GuestEnsureLeaseResponse:
    user, company = await _load_identity(
        container, user_id=body.user_id, company_id=body.company_id
    )
    async with guest_identity_scope(user=user, company=company):
        return await container.farm_service.ensure_lease(body)


@router.get("/runtimes/{flow_id}/{node_id}", response_model=GuestRuntimeStatusResponse)
async def guest_runtime_status(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
) -> GuestRuntimeStatusResponse:
    return await container.farm_service.status(flow_id, node_id)


@router.get("/runtimes/{flow_id}/{node_id}/logs", response_model=GuestRuntimeLogsResponse)
async def guest_runtime_logs(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
    task_id: Annotated[str | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    context_id: Annotated[str | None, Query()] = None,
) -> GuestRuntimeLogsResponse:
    try:
        return await container.farm_service.logs(
            flow_id,
            node_id,
            task_id=task_id,
            session_id=session_id,
            context_id=context_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/runtimes/{flow_id}/{node_id}", status_code=204)
async def drop_guest_runtime(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
) -> None:
    await container.farm_service.drop_runtime(flow_id, node_id)


@router.post("/a2a/{flow_id}/{node_id}")
async def guest_a2a(
    flow_id: str,
    node_id: str,
    rpc: JsonObject,
    container: ContainerDep,
) -> JsonObject:
    lease = await container.farm_service.get_lease(flow_id, node_id)
    if lease is None:
        raise HTTPException(status_code=404, detail="guest lease not found")
    user, company = await _load_identity(
        container, user_id=lease.user_id, company_id=lease.company_id
    )
    async with guest_identity_scope(user=user, company=company):
        return await container.farm_service.invoke_a2a(flow_id, node_id, rpc)

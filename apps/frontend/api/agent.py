"""HumanitecAgent settings API (REST-зеркало для frontend UI)."""

from fastapi import APIRouter, HTTPException

from apps.agent.models import (
    AgentAuditListResponse,
    AgentDeviceListItem,
    AgentDeviceListResponse,
    AgentReleaseStatusResponse,
    DevicePolicyUpdateRequest,
    PairingCodeResponse,
)
from apps.agent.service import (
    create_pairing_code,
    fetch_latest_release_status,
    is_device_tunnel_online,
    list_agent_audit_events,
    list_company_devices,
    revoke_device,
    update_device_policy,
)
from apps.frontend.dependencies import ContainerDep
from core.context import require_context

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/pairing", response_model=PairingCodeResponse, tags=["agent", "public"])
async def create_agent_pairing_code(container: ContainerDep) -> PairingCodeResponse:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return await create_pairing_code(
        container,
        user_id=context.user.user_id,
        company_id=company.company_id,
    )


@router.get("/devices", response_model=AgentDeviceListResponse, tags=["agent", "public"])
async def list_agent_devices(container: ContainerDep) -> AgentDeviceListResponse:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    items = await list_company_devices(
        container,
        company_id=company.company_id,
    )
    return AgentDeviceListResponse(items=items)


@router.delete("/devices/{device_id}", status_code=204, tags=["agent", "public"])
async def revoke_agent_device(device_id: str, container: ContainerDep) -> None:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    await revoke_device(
        container,
        device_id=device_id,
        company_id=company.company_id,
    )


@router.patch("/devices/{device_id}/policy", response_model=AgentDeviceListItem, tags=["agent", "public"])
async def update_agent_device_policy(
    device_id: str,
    body: DevicePolicyUpdateRequest,
    container: ContainerDep,
) -> AgentDeviceListItem:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    updated_device = await update_device_policy(
        container,
        device_id=device_id,
        company_id=company.company_id,
        policy=body.policy,
    )
    return AgentDeviceListItem(
        device_id=updated_device.device_id,
        device_name=updated_device.device_name,
        user_id=updated_device.user_id,
        company_id=updated_device.company_id,
        os=updated_device.os,
        hostname=updated_device.hostname,
        paired_at=updated_device.paired_at,
        last_seen_at=updated_device.last_seen_at,
        is_active=updated_device.is_active,
        is_tunnel_online=await is_device_tunnel_online(container, updated_device.device_id),
        policy=updated_device.policy,
    )


@router.get("/releases/status", response_model=AgentReleaseStatusResponse, tags=["agent", "public"])
async def agent_releases_status() -> AgentReleaseStatusResponse:
    return await fetch_latest_release_status()


@router.get("/audit", response_model=AgentAuditListResponse, tags=["agent", "public"])
async def list_agent_audit(
    container: ContainerDep,
    limit: int = 50,
) -> AgentAuditListResponse:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return await list_agent_audit_events(
        container,
        company_id=company.company_id,
        limit=limit,
    )

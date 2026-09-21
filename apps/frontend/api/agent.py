"""REST-зеркало команд `frontend/agent/*` (LinnexAgent в консоли компании) и публичный статус релизов."""

from fastapi import APIRouter

from apps.agent.models import (
    AgentAuditListResponse,
    AgentDeviceListItem,
    AgentDeviceListResponse,
    AgentReleaseStatusResponse,
    DevicePolicyUpdateRequest,
    PairingCodeResponse,
)
from apps.agent.service import fetch_latest_release_status
from apps.frontend.dependencies import ContainerDep
from apps.frontend.realtime.agent_operations import (
    AgentAuditListPayload,
    AgentDeviceIdPayload,
    AgentDevicePolicyUpdatePayload,
    AgentDeviceRevoked,
    AgentDevicesListPayload,
    op_agent_audit_list,
    op_agent_devices_list,
    op_agent_devices_policy_update,
    op_agent_devices_revoke,
    op_agent_pairing_create,
)
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/pairing", response_model=PairingCodeResponse, tags=["agent", "public"])
async def create_agent_pairing_code(container: ContainerDep) -> PairingCodeResponse:
    return await op_agent_pairing_create(EmptyPayload(), user=require_context().user, container=container)


@router.get("/devices", response_model=AgentDeviceListResponse, tags=["agent", "public"])
async def list_agent_devices(container: ContainerDep, mine: bool = False) -> AgentDeviceListResponse:
    return await op_agent_devices_list(
        AgentDevicesListPayload(mine=mine), user=require_context().user, container=container
    )


@router.delete("/devices/{device_id}", response_model=AgentDeviceRevoked, tags=["agent", "public"])
async def revoke_agent_device(device_id: str, container: ContainerDep) -> AgentDeviceRevoked:
    return await op_agent_devices_revoke(
        AgentDeviceIdPayload(device_id=device_id), user=require_context().user, container=container
    )


@router.patch("/devices/{device_id}/policy", response_model=AgentDeviceListItem, tags=["agent", "public"])
async def update_agent_device_policy(
    device_id: str, body: DevicePolicyUpdateRequest, container: ContainerDep
) -> AgentDeviceListItem:
    return await op_agent_devices_policy_update(
        AgentDevicePolicyUpdatePayload(device_id=device_id, policy=body.policy),
        user=require_context().user,
        container=container,
    )


@router.get("/releases/status", response_model=AgentReleaseStatusResponse, tags=["agent", "public"])
async def agent_releases_status(container: ContainerDep) -> AgentReleaseStatusResponse:
    """Публичный статус релизов десктопа (anonymous route, не команда)."""
    _ = container
    return await fetch_latest_release_status()


@router.get("/audit", response_model=AgentAuditListResponse, tags=["agent", "public"])
async def list_agent_audit(container: ContainerDep, limit: int = 50) -> AgentAuditListResponse:
    return await op_agent_audit_list(
        AgentAuditListPayload(limit=limit), user=require_context().user, container=container
    )

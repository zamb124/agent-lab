"""Команды LinnexAgent в консоли компании: pairing, устройства, политика, аудит.

Протокол устройства (download, discover, login-страница, device-token, register) и публичный
статус релизов — HTTP в `apps/frontend/api/agent_devices.py` / `agent.py`: их зовёт десктоп
и страница загрузки без сессии браузера.
"""

from __future__ import annotations

from pydantic import Field

from apps.agent.models import (
    AgentAuditListResponse,
    AgentDeviceListItem,
    AgentDeviceListResponse,
    DevicePolicyUpdateRequest,
    PairingCodeResponse,
)
from apps.agent.service import (
    create_pairing_code,
    is_device_tunnel_online,
    list_agent_audit_events,
    list_company_devices,
    revoke_device,
    update_device_policy,
)
from apps.frontend.di import Di
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.request_scope import require_company
from core.websocket import EmptyPayload


class AgentDevicesListPayload(StrictBaseModel):
    mine: bool = False


class AgentDeviceIdPayload(StrictBaseModel):
    device_id: str = Field(min_length=1)


class AgentDevicePolicyUpdatePayload(DevicePolicyUpdateRequest):
    device_id: str = Field(min_length=1)


class AgentDeviceRevoked(StrictBaseModel):
    device_id: str
    revoked: bool = True


class AgentAuditListPayload(StrictBaseModel):
    limit: int = Field(default=50, ge=1, le=500)


async def op_agent_pairing_create(
    payload: EmptyPayload, *, user: User, di: Di
) -> PairingCodeResponse:
    _ = payload
    scope = require_company()
    return await create_pairing_code(di, user_id=user.user_id, company_id=scope.company_id)


async def op_agent_devices_list(
    payload: AgentDevicesListPayload, *, user: User, di: Di
) -> AgentDeviceListResponse:
    scope = require_company()
    items = await list_company_devices(
        di,
        company_id=scope.company_id,
        viewer_user_id=user.user_id,
        owner_user_id=user.user_id if payload.mine else None,
    )
    return AgentDeviceListResponse(items=items)


async def op_agent_devices_revoke(
    payload: AgentDeviceIdPayload, *, user: User, di: Di
) -> AgentDeviceRevoked:
    scope = require_company()
    await revoke_device(
        di, device_id=payload.device_id, company_id=scope.company_id, actor_user_id=user.user_id
    )
    return AgentDeviceRevoked(device_id=payload.device_id)


async def op_agent_devices_policy_update(
    payload: AgentDevicePolicyUpdatePayload, *, user: User, di: Di
) -> AgentDeviceListItem:
    _ = user
    scope = require_company()
    updated_device = await update_device_policy(
        di, device_id=payload.device_id, company_id=scope.company_id, policy=payload.policy
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
        is_tunnel_online=await is_device_tunnel_online(di, updated_device.device_id),
        policy=updated_device.policy,
    )


async def op_agent_audit_list(
    payload: AgentAuditListPayload, *, user: User, di: Di
) -> AgentAuditListResponse:
    _ = user
    scope = require_company()
    return await list_agent_audit_events(di, company_id=scope.company_id, limit=payload.limit)

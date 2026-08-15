"""Agent device OpenFGA: owner/admin revoke, list filter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from apps.agent.authz.tuples import agent_device_company_link, agent_device_owner_tuple
from apps.agent.models import AgentDeviceRecord, DevicePolicy
from apps.agent.service import DEVICE_KEY_PREFIX, list_company_devices, revoke_device
from core.authz.company_sync import sync_company_member_roles
from core.authz.models import AuthzObject


@pytest.mark.asyncio
async def test_revoke_device_non_owner_member_forbidden(
    frontend_container,
    unique_id: str,
) -> None:
    company_id = f"agent_co_{unique_id}"
    owner_id = f"owner_{unique_id}"
    other_id = f"other_{unique_id}"
    device_id = f"device_{unique_id}"

    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=owner_id,
        roles=["member"],
    )
    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=other_id,
        roles=["member"],
    )

    record = AgentDeviceRecord(
        device_id=device_id,
        device_name="Laptop",
        user_id=owner_id,
        company_id=company_id,
        os="darwin",
        hostname="host",
        paired_at=datetime.now(timezone.utc),
        policy=DevicePolicy(),
        is_active=True,
    )
    _ = await frontend_container.shared_storage.set(
        f"{DEVICE_KEY_PREFIX}{device_id}",
        record.model_dump_json(),
        force_global=True,
    )
    await frontend_container.authz_service.write(
        [
            agent_device_company_link(device_id, company_id),
            agent_device_owner_tuple(device_id, owner_id),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await revoke_device(
            frontend_container,
            device_id=device_id,
            company_id=company_id,
            actor_user_id=other_id,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_devices_only_visible_to_owner(
    frontend_container,
    unique_id: str,
) -> None:
    company_id = f"agent_list_co_{unique_id}"
    owner_id = f"owner_{unique_id}"
    other_id = f"other_{unique_id}"
    device_id = f"device_list_{unique_id}"

    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=owner_id,
        roles=["member"],
    )
    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=other_id,
        roles=["member"],
    )

    record = AgentDeviceRecord(
        device_id=device_id,
        device_name="Phone",
        user_id=owner_id,
        company_id=company_id,
        os="ios",
        hostname="phone",
        paired_at=datetime.now(timezone.utc),
        policy=DevicePolicy(),
        is_active=True,
    )
    _ = await frontend_container.shared_storage.set(
        f"{DEVICE_KEY_PREFIX}{device_id}",
        record.model_dump_json(),
        force_global=True,
    )
    await frontend_container.authz_service.write(
        [
            agent_device_company_link(device_id, company_id),
            agent_device_owner_tuple(device_id, owner_id),
        ]
    )

    owner_items = await list_company_devices(
        frontend_container,
        company_id=company_id,
        viewer_user_id=owner_id,
    )
    other_items = await list_company_devices(
        frontend_container,
        company_id=company_id,
        viewer_user_id=other_id,
    )
    assert any(item.device_id == device_id for item in owner_items)
    assert all(item.device_id != device_id for item in other_items)


@pytest.mark.asyncio
async def test_revoke_keeps_owner_list_and_fga_tuples(
    frontend_container,
    unique_id: str,
) -> None:
    company_id = f"agent_rev_co_{unique_id}"
    owner_id = f"owner_{unique_id}"
    device_id = f"device_rev_{unique_id}"

    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=owner_id,
        roles=["member"],
    )

    record = AgentDeviceRecord(
        device_id=device_id,
        device_name="Laptop",
        user_id=owner_id,
        company_id=company_id,
        os="darwin",
        hostname="host",
        paired_at=datetime.now(timezone.utc),
        policy=DevicePolicy(),
        is_active=True,
    )
    _ = await frontend_container.shared_storage.set(
        f"{DEVICE_KEY_PREFIX}{device_id}",
        record.model_dump_json(),
        force_global=True,
    )
    await frontend_container.authz_service.write(
        [
            agent_device_company_link(device_id, company_id),
            agent_device_owner_tuple(device_id, owner_id),
        ]
    )

    await revoke_device(
        frontend_container,
        device_id=device_id,
        company_id=company_id,
        actor_user_id=owner_id,
    )

    items = await list_company_devices(
        frontend_container,
        company_id=company_id,
        viewer_user_id=owner_id,
    )
    matched = next(item for item in items if item.device_id == device_id)
    assert matched.is_active is False
    assert matched.is_tunnel_online is False
    remaining = await frontend_container.authz_service.list_tuples(
        AuthzObject.agent_device(device_id)
    )
    assert remaining

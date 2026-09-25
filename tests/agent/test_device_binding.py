"""Tests for bind_user_device_variables / resolve_user_online_device."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.agent.device_binding import (
    bind_user_device_variables,
    resolve_user_online_device,
)
from apps.agent.models import AgentDeviceRecord, DevicePolicy
from apps.agent.service import DEVICE_KEY_PREFIX, TUNNEL_ONLINE_PREFIX
from core.types import JsonObject


async def _seed_device(
    storage,
    *,
    device_id: str,
    user_id: str,
    company_id: str,
    device_name: str,
    last_seen_at: datetime,
    online: bool,
    is_active: bool = True,
) -> None:
    record = AgentDeviceRecord(
        device_id=device_id,
        device_name=device_name,
        user_id=user_id,
        company_id=company_id,
        os="darwin",
        hostname=f"host-{device_id}",
        paired_at=last_seen_at - timedelta(days=1),
        last_seen_at=last_seen_at,
        is_active=is_active,
        policy=DevicePolicy(),
        active_device_jti=f"jti-{device_id}",
    )
    await storage.set(
        f"{DEVICE_KEY_PREFIX}{device_id}",
        record.model_dump_json(),
        force_global=True,
    )
    online_key = f"{TUNNEL_ONLINE_PREFIX}{device_id}"
    if online:
        await storage.set(
            online_key,
            '{"device_id":"%s"}' % device_id,
            ttl=120,
            force_global=True,
        )
    else:
        await storage.delete(online_key, force_global=True)


@pytest.mark.asyncio
async def test_resolve_user_online_device_picks_newest(
    frontend_di,
    unique_id: str,
) -> None:
    storage = frontend_di.shared_storage
    company_id = f"co-{unique_id}"
    user_id = f"user-{unique_id}"
    now = datetime.now(timezone.utc)
    await _seed_device(
        storage,
        device_id=f"old-{unique_id}",
        user_id=user_id,
        company_id=company_id,
        device_name="Old Mac",
        last_seen_at=now - timedelta(minutes=10),
        online=True,
    )
    await _seed_device(
        storage,
        device_id=f"new-{unique_id}",
        user_id=user_id,
        company_id=company_id,
        device_name="New Mac",
        last_seen_at=now,
        online=True,
    )
    await _seed_device(
        storage,
        device_id=f"offline-{unique_id}",
        user_id=user_id,
        company_id=company_id,
        device_name="Offline",
        last_seen_at=now + timedelta(minutes=1),
        online=False,
    )
    await _seed_device(
        storage,
        device_id=f"other-{unique_id}",
        user_id=f"other-{unique_id}",
        company_id=company_id,
        device_name="Other User",
        last_seen_at=now + timedelta(hours=1),
        online=True,
    )

    resolved = await resolve_user_online_device(
        storage,
        company_id=company_id,
        user_id=user_id,
    )
    assert resolved is not None
    assert resolved.device_id == f"new-{unique_id}"
    assert resolved.device_name == "New Mac"


@pytest.mark.asyncio
async def test_bind_rejects_foreign_device_id_and_auto_binds(
    frontend_di,
    unique_id: str,
) -> None:
    storage = frontend_di.shared_storage
    company_id = f"co-{unique_id}"
    user_id = f"user-{unique_id}"
    now = datetime.now(timezone.utc)
    await _seed_device(
        storage,
        device_id=f"mine-{unique_id}",
        user_id=user_id,
        company_id=company_id,
        device_name="Mine",
        last_seen_at=now,
        online=True,
    )
    await _seed_device(
        storage,
        device_id=f"foreign-{unique_id}",
        user_id=f"other-{unique_id}",
        company_id=company_id,
        device_name="Foreign",
        last_seen_at=now,
        online=True,
    )

    variables: JsonObject = {
        "device_id": f"foreign-{unique_id}",
        "device_name": "spoof",
        "linnex_agent_client": "",
    }
    await bind_user_device_variables(
        variables,
        storage,
        company_id=company_id,
        user_id=user_id,
    )
    assert variables["device_id"] == f"mine-{unique_id}"
    assert variables["device_name"] == "Mine"
    assert variables["linnex_agent_client"] == "spa"


@pytest.mark.asyncio
async def test_bind_keeps_linnex_agent_client_from_desktop(
    frontend_di,
    unique_id: str,
) -> None:
    storage = frontend_di.shared_storage
    company_id = f"co-{unique_id}"
    user_id = f"user-{unique_id}"
    device_id = f"desk-{unique_id}"
    now = datetime.now(timezone.utc)
    await _seed_device(
        storage,
        device_id=device_id,
        user_id=user_id,
        company_id=company_id,
        device_name="Desktop",
        last_seen_at=now,
        online=True,
    )
    variables: JsonObject = {
        "device_id": device_id,
        "device_name": "",
        "linnex_agent_client": "linnex_agent",
    }
    await bind_user_device_variables(
        variables,
        storage,
        company_id=company_id,
        user_id=user_id,
    )
    assert variables["device_id"] == device_id
    assert variables["device_name"] == "Desktop"
    assert variables["linnex_agent_client"] == "linnex_agent"


@pytest.mark.asyncio
async def test_bind_clears_when_no_online_device(
    frontend_di,
    unique_id: str,
) -> None:
    storage = frontend_di.shared_storage
    variables: JsonObject = {"device_id": "", "device_name": "x"}
    await bind_user_device_variables(
        variables,
        storage,
        company_id=f"co-{unique_id}",
        user_id=f"user-{unique_id}",
    )
    assert variables["device_id"] == ""
    assert variables["device_name"] == ""

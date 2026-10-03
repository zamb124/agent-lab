"""Привязка online LinnexAgent к session variables любого flow (SPA / A2A) без device JWT.

Standing tools ``device_tools_*`` опциональны в любом flow; у Lara они стоят по умолчанию.
``device_id`` в variables — общий контракт для этих tools.
"""

from __future__ import annotations

from datetime import datetime

from apps.agent.device_query import DEVICE_KEY_PREFIX
from apps.agent.models import AgentDeviceListItem, AgentDeviceRecord
from apps.agent.service import device_tunnel_is_online
from core.db.storage import Storage
from core.types import JsonObject

_LINNEX_AGENT_CLIENT = "linnex_agent"
_SPA_CLIENT = "spa"


async def resolve_user_online_device(
    storage: Storage,
    *,
    company_id: str,
    user_id: str,
) -> AgentDeviceListItem | None:
    """Самое свежее online-устройство пользователя в компании (по last_seen_at)."""
    records = await storage.get_all_by_prefix(
        DEVICE_KEY_PREFIX,
        limit=1000,
    )
    best: AgentDeviceListItem | None = None
    best_seen: datetime | None = None
    for storage_key, raw_value in records.items():
        if not storage_key.startswith(DEVICE_KEY_PREFIX):
            continue
        device = AgentDeviceRecord.model_validate_json(raw_value)
        if device.company_id != company_id:
            continue
        if device.user_id != user_id:
            continue
        if not device.is_active:
            continue
        if not await device_tunnel_is_online(storage, device.device_id):
            continue
        item = AgentDeviceListItem(
            device_id=device.device_id,
            device_name=device.device_name,
            user_id=device.user_id,
            company_id=device.company_id,
            os=device.os,
            hostname=device.hostname,
            paired_at=device.paired_at,
            last_seen_at=device.last_seen_at,
            is_active=device.is_active,
            is_tunnel_online=True,
            policy=device.policy,
        )
        seen = device.last_seen_at
        if best is None:
            best = item
            best_seen = seen
            continue
        if seen is None:
            continue
        if best_seen is None or seen > best_seen:
            best = item
            best_seen = seen
    return best


async def _load_owned_active_device(
    storage: Storage,
    *,
    device_id: str,
    company_id: str,
    user_id: str,
) -> AgentDeviceRecord | None:
    raw_value = await storage.get(
        f"{DEVICE_KEY_PREFIX}{device_id}",
    )
    if raw_value is None:
        return None
    device = AgentDeviceRecord.model_validate_json(raw_value)
    if device.company_id != company_id:
        return None
    if device.user_id != user_id:
        return None
    if not device.is_active:
        return None
    return device


def _clear_device_binding(variables: JsonObject) -> None:
    variables["device_id"] = ""
    variables["device_name"] = ""


def _apply_device_binding(
    variables: JsonObject,
    *,
    device_id: str,
    device_name: str,
    prefer_spa_client: bool,
) -> None:
    variables["device_id"] = device_id
    variables["device_name"] = device_name
    if "linnex_agent_client" not in variables:
        return
    existing_client = variables.get("linnex_agent_client")
    if existing_client == _LINNEX_AGENT_CLIENT:
        return
    if prefer_spa_client:
        variables["linnex_agent_client"] = _SPA_CLIENT


async def bind_user_device_variables(
    variables: JsonObject,
    storage: Storage,
    *,
    company_id: str,
    user_id: str,
) -> None:
    """Fail-closed bind для любого flow: чужой device_id сбрасывается; пустой — auto online."""
    claimed_raw = variables.get("device_id")
    if isinstance(claimed_raw, str) and claimed_raw.strip():
        claimed_id = claimed_raw.strip()
        owned = await _load_owned_active_device(
            storage,
            device_id=claimed_id,
            company_id=company_id,
            user_id=user_id,
        )
        if owned is None:
            _clear_device_binding(variables)
        else:
            prefer_spa = variables.get("linnex_agent_client") != _LINNEX_AGENT_CLIENT
            _apply_device_binding(
                variables,
                device_id=owned.device_id,
                device_name=owned.device_name,
                prefer_spa_client=prefer_spa,
            )
            return

    resolved = await resolve_user_online_device(
        storage,
        company_id=company_id,
        user_id=user_id,
    )
    if resolved is None:
        _clear_device_binding(variables)
        return
    _apply_device_binding(
        variables,
        device_id=resolved.device_id,
        device_name=resolved.device_name,
        prefer_spa_client=True,
    )

"""Запросы device records без циклических зависимостей service ↔ tunnel_bus."""

from __future__ import annotations

from apps.agent.models import AgentDeviceRecord
from core.db.storage import Storage

DEVICE_KEY_PREFIX = "agent_device:"


async def list_active_device_ids_for_company(
    storage: Storage,
    company_id: str,
) -> list[str]:
    records = await storage.get_all_by_prefix(
        DEVICE_KEY_PREFIX,
        limit=1000,
        force_global=True,
    )
    device_ids: list[str] = []
    for storage_key, raw_value in records.items():
        if not storage_key.startswith(DEVICE_KEY_PREFIX):
            continue
        device = AgentDeviceRecord.model_validate_json(raw_value)
        if device.company_id != company_id:
            continue
        if not device.is_active:
            continue
        device_ids.append(device.device_id)
    return device_ids

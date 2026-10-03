"""Backfill OpenFGA tuples for agent devices from the shared storage table."""

from __future__ import annotations

import asyncio
import sys

from apps.agent.authz.tuples import agent_device_company_link, agent_device_owner_tuple
from apps.agent.di import AgentDi
from apps.agent.models import AgentDeviceRecord
from core.authz.backfill_limit import parse_backfill_limit
from core.authz.service import AuthzService
from core.config import get_settings
from core.db.storage import SharedStorage
from core.di import ProcessIdentity, open_di
from core.logging import get_logger

logger = get_logger(__name__)

DEVICE_KEY_PREFIX = "agent_device:"


async def backfill_agent_devices(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for agent device backfill")
    if not settings.database.shared_url:
        raise RuntimeError("database.shared_url is required for agent device backfill")

    identity = ProcessIdentity(service_name="agent", files_route_segment="agent")
    async with open_di(
        AgentDi,
        settings=settings,
        identity=identity,
        database="shared_url",
    ) as di:
        if not di.authz_service.enabled:
            raise RuntimeError("openfga.enabled must be true for agent device backfill")
        return await _write_device_tuples(
            di.authz_service,
            di.shared_storage,
            limit=limit,
        )


async def _write_device_tuples(
    authz: AuthzService,
    storage: SharedStorage,
    *,
    limit: int | None,
) -> int:
    records = await storage.get_all_by_prefix(
        DEVICE_KEY_PREFIX,
        limit=10_000,
    )
    written = 0
    try:
        for storage_key, raw_value in records.items():
            if limit is not None and written >= limit:
                break
            if not storage_key.startswith(DEVICE_KEY_PREFIX):
                continue
            device = AgentDeviceRecord.model_validate_json(raw_value)
            if not device.is_active:
                continue
            await authz.write(
                [
                    agent_device_company_link(device.device_id, device.company_id),
                    agent_device_owner_tuple(device.device_id, device.user_id),
                ]
            )
            written += 1
    finally:
        await authz.close()
    logger.info("agent.device.backfill.complete.devices", devices=written)
    return written


def main(argv: list[str] | None = None) -> int:
    limit = parse_backfill_limit("Backfill agent devices into OpenFGA", argv)
    written = asyncio.run(backfill_agent_devices(limit=limit))
    _ = sys.stdout.write(f"synced={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

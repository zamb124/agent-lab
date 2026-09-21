"""Backfill OpenFGA tuples for agent devices from Redis/shared storage."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from apps.agent.authz.tuples import agent_device_company_link, agent_device_owner_tuple
from apps.agent.models import AgentDeviceRecord
from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.storage import Storage
from core.logging import get_logger

logger = get_logger(__name__)

DEVICE_KEY_PREFIX = "agent_device:"


async def backfill_agent_devices(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for agent device backfill")
    if not settings.database.shared_url:
        raise RuntimeError("database.shared_url is required for agent device backfill")

    authz = build_authz_service()
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for agent device backfill")

    storage = Storage(db_url=str(settings.database.shared_url))
    records = await storage.get_all_by_prefix(
        DEVICE_KEY_PREFIX,
        limit=10_000,
        force_global=True,
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
    parser = argparse.ArgumentParser(description="Backfill agent devices into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit = cast(int | None, args.limit)
    written = asyncio.run(backfill_agent_devices(limit=limit))
    _ = sys.stdout.write(f"synced={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

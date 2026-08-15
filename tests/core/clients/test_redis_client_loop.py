"""RedisClient переживает смену asyncio event loop (Starlette TestClient)."""

from __future__ import annotations

import asyncio

import pytest

from core.clients.redis_client import RedisClient
from core.config import get_settings

pytestmark = pytest.mark.timeout(15, func_only=True)


def test_redis_client_reconnects_after_event_loop_change(unique_id: str) -> None:
    """Два asyncio.run — два loop; PING/GET не падают Future attached to a different loop."""
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise RuntimeError("database.redis_url is required")
    client = RedisClient(redis_url)
    key = f"redis_loop_test:{unique_id}"

    async def write_on_first_loop() -> None:
        _ = await client.delete(key)
        wrote = await client.set(key, "from-first-loop", ttl=60)
        assert wrote is True

    asyncio.run(write_on_first_loop())

    async def read_on_second_loop() -> None:
        value = await client.get(key)
        assert value == "from-first-loop"
        _ = await client.delete(key)
        await client.close()

    asyncio.run(read_on_second_loop())

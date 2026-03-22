"""dispatch_sync_command публикует JSON в Redis sync.realtime.events."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import redis.asyncio as redis

from core.config import get_settings
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope


@pytest.mark.asyncio
async def test_dispatch_sync_command_publishes_realtime_event_to_redis(company_id: str) -> None:
    settings = get_settings()
    r = redis.from_url(settings.database.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe("sync.realtime.events")

    q: asyncio.Queue[dict] = asyncio.Queue()

    async def _listen() -> None:
        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue
            data = raw.get("data")
            if data is None:
                continue
            if isinstance(data, bytes):
                parsed = json.loads(data.decode("utf-8"))
            else:
                parsed = json.loads(data)
            await q.put(parsed)
            return

    listen_task = asyncio.create_task(_listen())
    await asyncio.sleep(0.05)

    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id="u1",
        company_id=company_id,
        type="spaces.create",
        payload={"body": {"name": "RedisSpace", "description": None}},
    )
    out = await dispatch_sync_command(cmd)
    assert out["ok"] is True

    payload = await asyncio.wait_for(q.get(), timeout=10.0)
    listen_task.cancel()
    try:
        await listen_task
    except asyncio.CancelledError:
        pass

    assert payload["type"] == "space.created"
    assert payload["payload"]["name"] == "RedisSpace"

    await pubsub.unsubscribe("sync.realtime.events")
    await pubsub.aclose()
    await r.aclose()

"""dispatch_sync_command публикует UIEvent в платформенный канал `platform:ui_events`.

Все push-события Sync идут через `core.ui_events.publish_ui_event_*` ->
`platform:ui_events`. Подписку форвардит `notification_manager.start_redis_listener`
в подключённые сокеты `/sync/api/ws/notifications`. Этот тест проверяет
нижний слой: `dispatch_sync_command` действительно публикует кадр в общий канал.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import redis.asyncio as redis

from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from core.config import get_settings
from core.ui_events.dispatcher import UI_EVENTS_REDIS_CHANNEL


@pytest.mark.asyncio
async def test_dispatch_sync_command_publishes_to_platform_ui_events(company_id: str) -> None:
    settings = get_settings()
    r = redis.from_url(settings.database.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(UI_EVENTS_REDIS_CHANNEL)

    q: asyncio.Queue[dict] = asyncio.Queue()

    async def _listen() -> None:
        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue
            data = raw.get("data")
            if data is None:
                continue
            if isinstance(data, bytes):
                envelope = json.loads(data.decode("utf-8"))
            else:
                envelope = json.loads(data)
            event = envelope.get("event")
            if not isinstance(event, dict):
                continue
            if event.get("type") == "sync/space/created":
                await q.put(envelope)
                return

    listen_task = asyncio.create_task(_listen())
    await asyncio.sleep(0.05)

    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id="u1",
        company_id=company_id,
        type="spaces.create",
        payload={"body": {"name": "PlatformSpace", "description": None}},
    )
    out = await dispatch_sync_command(cmd)
    assert out["ok"] is True

    envelope = await asyncio.wait_for(q.get(), timeout=10.0)
    listen_task.cancel()
    try:
        await listen_task
    except asyncio.CancelledError:
        pass

    target = envelope.get("target") or {}
    assert target.get("company_id") == company_id, "broadcast по компании"
    event = envelope["event"]
    assert event["type"] == "sync/space/created"
    assert event["payload"]["name"] == "PlatformSpace"

    await pubsub.unsubscribe(UI_EVENTS_REDIS_CHANNEL)
    await pubsub.aclose()
    await r.aclose()

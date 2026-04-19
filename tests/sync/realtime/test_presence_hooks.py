"""Sync presence через core.websocket connect/disconnect hooks.

Тест проверяет, что hook'и (`apps.sync.realtime.presence_hooks._on_connect`/
`_on_disconnect`) обновляют Redis-presence ключ и публикуют push-событие
`sync/presence/changed` через `platform:ui_events`.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import redis.asyncio as redis

from apps.sync.realtime.presence_hooks import _on_connect, _on_disconnect
from apps.sync.ws_presence import is_user_sync_ws_online
from core.config import get_settings
from core.ui_events.dispatcher import UI_EVENTS_REDIS_CHANNEL


async def _wait_presence_event(channel_pubsub, timeout: float = 10.0) -> dict:
    async def _listen() -> dict:
        async for raw in channel_pubsub.listen():
            if raw["type"] != "message":
                continue
            data = raw.get("data")
            if data is None:
                continue
            envelope = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
            event = envelope.get("event")
            if isinstance(event, dict) and event.get("type") == "sync/presence/changed":
                return envelope
        raise RuntimeError("subscription closed")

    return await asyncio.wait_for(_listen(), timeout=timeout)


@pytest.mark.asyncio
async def test_on_connect_first_publishes_presence_online(
    company_id: str,
    unique_id: str,
) -> None:
    settings = get_settings()
    user_id = f"presence_user_{unique_id}"
    r = redis.from_url(settings.database.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(UI_EVENTS_REDIS_CHANNEL)
    await asyncio.sleep(0.05)

    listen_task = asyncio.create_task(_wait_presence_event(pubsub))
    try:
        await _on_connect(user_id, company_id, was_first=True)

        envelope = await listen_task
        target = envelope.get("target") or {}
        assert target.get("company_id") == company_id
        payload = envelope["event"]["payload"]
        assert payload["user_id"] == user_id
        assert payload["online"] is True

        assert await is_user_sync_ws_online(settings.database.redis_url, user_id) is True
    finally:
        await pubsub.unsubscribe(UI_EVENTS_REDIS_CHANNEL)
        await pubsub.aclose()
        await r.aclose()


@pytest.mark.asyncio
async def test_on_connect_second_does_not_publish(
    company_id: str,
    unique_id: str,
) -> None:
    """При не-первом подключении hook не публикует событие."""
    settings = get_settings()
    user_id = f"presence_user_second_{unique_id}"
    r = redis.from_url(settings.database.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(UI_EVENTS_REDIS_CHANNEL)
    await asyncio.sleep(0.05)
    try:
        await _on_connect(user_id, company_id, was_first=False)
        await asyncio.sleep(0.5)

        msg = await asyncio.wait_for(pubsub.get_message(timeout=0.5), timeout=1.0)
        if msg and msg.get("type") == "message":
            envelope = json.loads(
                msg["data"].decode("utf-8") if isinstance(msg["data"], bytes) else msg["data"]
            )
            event = envelope.get("event") or {}
            payload = event.get("payload") or {}
            assert payload.get("user_id") != user_id, "не первый connect не должен публиковать"
    finally:
        await pubsub.unsubscribe(UI_EVENTS_REDIS_CHANNEL)
        await pubsub.aclose()
        await r.aclose()


@pytest.mark.asyncio
async def test_on_disconnect_last_publishes_presence_offline(
    company_id: str,
    unique_id: str,
) -> None:
    settings = get_settings()
    user_id = f"presence_user_offline_{unique_id}"
    await _on_connect(user_id, company_id, was_first=True)

    r = redis.from_url(settings.database.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(UI_EVENTS_REDIS_CHANNEL)
    await asyncio.sleep(0.05)

    listen_task = asyncio.create_task(_wait_presence_event(pubsub))
    try:
        await _on_disconnect(user_id, company_id, was_last=True)

        envelope = await listen_task
        payload = envelope["event"]["payload"]
        assert payload["user_id"] == user_id
        assert payload["online"] is False
        assert payload["last_seen_at"] is not None

        assert await is_user_sync_ws_online(settings.database.redis_url, user_id) is False
    finally:
        await pubsub.unsubscribe(UI_EVENTS_REDIS_CHANNEL)
        await pubsub.aclose()
        await r.aclose()


@pytest.mark.asyncio
async def test_on_disconnect_not_last_does_nothing(
    company_id: str,
    unique_id: str,
) -> None:
    settings = get_settings()
    user_id = f"presence_user_not_last_{unique_id}"
    await _on_connect(user_id, company_id, was_first=True)

    r = redis.from_url(settings.database.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(UI_EVENTS_REDIS_CHANNEL)
    await asyncio.sleep(0.05)
    try:
        await _on_disconnect(user_id, company_id, was_last=False)
        assert await is_user_sync_ws_online(settings.database.redis_url, user_id) is True
    finally:
        await pubsub.unsubscribe(UI_EVENTS_REDIS_CHANNEL)
        await pubsub.aclose()
        await r.aclose()

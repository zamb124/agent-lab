"""Фикстуры HTTP/WS-тестов sync.

Все фикстуры — без моков и monkeypatch. Подписки на Redis Pub/Sub —
реальный `redis.asyncio` к тестовому Redis (порт `63792`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest_asyncio
import redis.asyncio as redis_async

from core.config import get_settings

UiEventsReceive = Callable[[str, str | None, float], Awaitable[list[dict[str, Any]]]]


@pytest_asyncio.fixture()
async def ui_events_listener() -> AsyncIterator[UiEventsReceive]:
    """Подписка на `platform:ui_events`; возвращает функцию ожидания событий.

    Сигнатура: `(event_type: str, target_user_id: str | None, timeout: float)`
    → `list[event]`. Если `target_user_id` задан — фильтрует ещё и по
    `target.user_id` в конверте (см. `core.ui_events.dispatcher._envelope`),
    что нужно для проверок «прилетело конкретно user2». Если `None` —
    возвращает все события указанного `event_type` независимо от target.

    Конверт в `platform:ui_events`:
        {"target": {"user_id": "..." | "company_id": "..." | "broadcast": True},
         "event": {"id": ..., "type": ..., "payload": ...}}
    """
    settings = get_settings()
    if not settings.database.redis_url:
        raise RuntimeError("database.redis_url не задан для ui_events_listener.")

    client = redis_async.from_url(settings.database.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe("platform:ui_events")
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

    async def _receive(
        filter_type: str,
        target_user_id: str | None,
        timeout: float,
    ) -> list[dict[str, Any]]:
        deadline = asyncio.get_event_loop().time() + timeout
        collected: list[dict[str, Any]] = []
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=min(remaining, 0.5),
            )
            if msg is None:
                continue
            data = msg.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            if not isinstance(data, str):
                continue
            try:
                envelope = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(envelope, dict):
                continue
            target = envelope.get("target")
            event = envelope.get("event")
            if not isinstance(target, dict) or not isinstance(event, dict):
                continue
            if event.get("type") != filter_type:
                continue
            if target_user_id is not None and target.get("user_id") != target_user_id:
                continue
            collected.append(event)
        return collected

    try:
        yield _receive
    finally:
        await pubsub.unsubscribe("platform:ui_events")
        await pubsub.aclose()
        await client.aclose()

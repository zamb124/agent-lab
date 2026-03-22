"""Публикация realtime-событий в Redis (общая точка для команд и REST)."""

from __future__ import annotations

import json

import redis.asyncio as redis

from core.config import get_settings
from apps.sync.realtime.events import RealtimeEvent


async def publish_realtime_events(events: list[RealtimeEvent]) -> None:
    if not events:
        return
    settings = get_settings()
    r = redis.from_url(settings.database.redis_url)
    try:
        for event in events:
            await r.publish(
                "sync.realtime.events",
                json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
            )
    finally:
        await r.aclose()

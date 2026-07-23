"""Общий листенер шины `platform:events` для тестов.

Читает Redis Stream с момента открытия. Контракт receive-функции:
`(event_type, target_user_id | None, timeout)` → `list[event]`, где event —
сериализованный `PlatformEvent` (`event_id`, `type`, `company_id`, `payload`,
`meta`, `delivery`). Фильтр по `target_user_id` — членство в
`delivery.user_ids` (не legacy `target.user_id` из старого Pub/Sub-конверта).

Единственное имя listener-фикстуры — `platform_events_listener`.
Сервисные conftest могут реэкспортировать тот же callable без `*_ui_events_*`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis_async

from core.config import get_settings
from core.events import PLATFORM_EVENTS_STREAM

PlatformEventsReceive = Callable[[str, str | None, float], Awaitable[list[dict[str, Any]]]]


def _delivery_matches_user(event: dict[str, Any], target_user_id: str) -> bool:
    delivery = event.get("delivery")
    if not isinstance(delivery, dict):
        return False
    user_ids = delivery.get("user_ids")
    return isinstance(user_ids, list) and target_user_id in user_ids


@asynccontextmanager
async def platform_events_listener() -> AsyncIterator[PlatformEventsReceive]:
    """Открыть листенер шины; события до открытия не читаются."""
    settings = get_settings()
    if not settings.database.redis_url:
        raise RuntimeError("database.redis_url не задан для platform_events_listener.")

    client = redis_async.from_url(settings.database.redis_url, decode_responses=True)
    stream_info_last_id = "$"
    last_entries = await client.xrevrange(PLATFORM_EVENTS_STREAM, count=1)
    if last_entries:
        stream_info_last_id = last_entries[0][0]
    state = {"last_id": stream_info_last_id}

    async def _receive(
        filter_type: str,
        target_user_id: str | None,
        timeout: float,
    ) -> list[dict[str, Any]]:
        deadline = asyncio.get_event_loop().time() + timeout
        collected: list[dict[str, Any]] = []
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            read_result = await client.xread(
                {PLATFORM_EVENTS_STREAM: state["last_id"]},
                count=100,
                block=max(int(min(remaining, 0.5) * 1000), 1),
            )
            if not read_result:
                continue
            for _stream_name, entries in read_result:
                for entry_id, fields in entries:
                    state["last_id"] = entry_id
                    raw_event = fields.get("event")
                    if not isinstance(raw_event, str):
                        continue
                    try:
                        event = json.loads(raw_event)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") != filter_type:
                        continue
                    if target_user_id is not None and not _delivery_matches_user(
                        event, target_user_id
                    ):
                        continue
                    collected.append(event)
        return collected

    try:
        yield _receive
    finally:
        await client.aclose()

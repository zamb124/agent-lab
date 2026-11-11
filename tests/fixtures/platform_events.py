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
from typing import Any, cast

import redis.asyncio as redis_async

from core.config import get_settings
from core.events import PLATFORM_EVENTS_STREAM

PlatformEventsReceive = Callable[[str, str | None, float], Awaitable[list[dict[str, Any]]]]


# Redis XREAD `$` = только сообщения ПОСЛЕ этого вызова. Если стрим пуст и
# publish случился между xrevrange и первым xread — событие теряется.
_EMPTY_STREAM_CURSOR = "0-0"


def initial_platform_events_cursor(last_entry_id: str | None) -> str:
    """Курсор «с этого момента»: конкретный id или начало пустого стрима."""
    if last_entry_id is None:
        return _EMPTY_STREAM_CURSOR
    return last_entry_id


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
    last_entries = await client.xrevrange(PLATFORM_EVENTS_STREAM, count=1)
    last_entry_id = str(last_entries[0][0]) if last_entries else None
    state = {"last_id": initial_platform_events_cursor(last_entry_id)}

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
                stream_entries = cast(list[tuple[Any, dict[str, Any]]], entries)
                for entry_id, fields in stream_entries:
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


async def wait_platform_event_payload(
    receive: PlatformEventsReceive,
    event_type: str,
    *,
    timeout: float,
    match: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Ждёт событие ``event_type``, payload которого удовлетворяет ``match``.

    ``receive`` читает стрим порциями до таймаута; короткие чтения подряд не
    теряют события (курсор двигается внутри листенера), поэтому выходим сразу
    по совпадению, а не ждём весь ``timeout``.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        events = await receive(event_type, None, 2.0)
        for event in events:
            payload = event.get("payload")
            if isinstance(payload, dict) and match(payload):
                return payload
        if asyncio.get_event_loop().time() >= deadline:
            raise AssertionError(f"{event_type} не пришёл за {timeout}с")

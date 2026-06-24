"""Ожидание push-событий worktracker в Redis."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


async def wait_work_item_event(
    listener: Callable[[str, str | None, float], Awaitable[list[dict[str, Any]]]],
    event_type: str,
    work_item_id: str,
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    events = await listener(event_type, None, timeout)
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        work_item = payload.get("work_item")
        if isinstance(work_item, dict) and work_item.get("work_item_id") == work_item_id:
            return event
        if payload.get("work_item_id") == work_item_id:
            return event
    raise AssertionError(
        f"Событие {event_type!r} для work_item_id={work_item_id!r} не получено за {timeout}s"
    )

"""Публикация realtime-событий Sync через шину `platform:events`."""

from __future__ import annotations

from core.events import publish_event
from core.events.contract import PlatformEvent


async def publish_realtime_events(events: list[PlatformEvent]) -> None:
    if not events:
        return
    for event in events:
        await publish_event(event)

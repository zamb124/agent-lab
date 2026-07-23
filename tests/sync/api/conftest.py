"""Фикстуры HTTP/WS-тестов sync.

Все фикстуры — без моков и monkeypatch. Чтение шины `platform:events` —
реальный `redis.asyncio` к тестовому Redis (порт `63792`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from tests.fixtures.platform_events import (
    PlatformEventsReceive,
    platform_events_listener as open_platform_events_stream,
)


@pytest_asyncio.fixture()
async def platform_events_listener() -> AsyncIterator[PlatformEventsReceive]:
    """Листенер шины Redis `platform:events`.

    Сигнатура: `(event_type: str, target_user_id: str | None, timeout: float)`
    → `list[event]`. Если `target_user_id` задан — фильтрует по членству в
    `delivery.user_ids` события. Если `None` — все события указанного `event_type`.
    """
    async with open_platform_events_stream() as receive:
        yield receive

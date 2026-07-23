"""Sync presence через core.websocket connect/disconnect hooks.

Тест проверяет, что hook'и (`apps.sync.realtime.presence_hooks._on_connect`/
`_on_disconnect`) обновляют Redis-presence ключ и публикуют push-событие
`sync/presence/changed` через шину `platform:events`.
"""

from __future__ import annotations

import pytest

from apps.sync.realtime.presence_hooks import _on_connect, _on_disconnect
from apps.sync.ws_presence import is_user_sync_ws_online
from core.config import get_settings
from tests.fixtures.platform_events import platform_events_listener


def _presence_events_for_user(events: list[dict], user_id: str) -> list[dict]:
    matched: list[dict] = []
    for event in events:
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("user_id") == user_id:
            matched.append(event)
    return matched


@pytest.mark.asyncio
async def test_on_connect_first_publishes_presence_online(
    company_id: str,
    unique_id: str,
) -> None:
    settings = get_settings()
    user_id = f"presence_user_{unique_id}"
    async with platform_events_listener() as receive:
        await _on_connect(user_id, company_id, was_first=True)

        events = await receive("sync/presence/changed", None, 2.0)
        matched = _presence_events_for_user(events, user_id)
        assert matched, "ожидалось событие sync/presence/changed для user_id"
        event = matched[0]
        delivery = event.get("delivery")
        assert isinstance(delivery, dict) and delivery.get("company_id") == company_id
        payload = event["payload"]
        assert payload["user_id"] == user_id
        assert payload["online"] is True

        assert await is_user_sync_ws_online(settings.database.redis_url, user_id) is True


@pytest.mark.asyncio
async def test_on_connect_second_does_not_publish(
    company_id: str,
    unique_id: str,
) -> None:
    """При не-первом подключении hook не публикует событие."""
    user_id = f"presence_user_second_{unique_id}"
    async with platform_events_listener() as receive:
        await _on_connect(user_id, company_id, was_first=False)
        events = await receive("sync/presence/changed", None, 1.0)
        assert _presence_events_for_user(events, user_id) == [], (
            "не первый connect не должен публиковать"
        )


@pytest.mark.asyncio
async def test_on_disconnect_last_publishes_presence_offline(
    company_id: str,
    unique_id: str,
) -> None:
    settings = get_settings()
    user_id = f"presence_user_offline_{unique_id}"
    await _on_connect(user_id, company_id, was_first=True)

    async with platform_events_listener() as receive:
        await _on_disconnect(user_id, company_id, was_last=True)

        events = await receive("sync/presence/changed", None, 2.0)
        matched = _presence_events_for_user(events, user_id)
        assert matched, "ожидалось событие sync/presence/changed для user_id"
        payload = matched[0]["payload"]
        assert payload["user_id"] == user_id
        assert payload["online"] is False
        assert payload["last_seen_at"] is not None

        assert await is_user_sync_ws_online(settings.database.redis_url, user_id) is False


@pytest.mark.asyncio
async def test_on_disconnect_not_last_does_nothing(
    company_id: str,
    unique_id: str,
) -> None:
    settings = get_settings()
    user_id = f"presence_user_not_last_{unique_id}"
    await _on_connect(user_id, company_id, was_first=True)

    await _on_disconnect(user_id, company_id, was_last=False)
    assert await is_user_sync_ws_online(settings.database.redis_url, user_id) is True

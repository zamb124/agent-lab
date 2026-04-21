"""Платформенные уведомления sync (notify_user через TaskIQ): правила skip.

Все компоненты — реальные (PostgreSQL, Redis, TaskIQ worker, sync_service).
Никаких моков и monkeypatch. Принцип проверки:

  - Подписываемся на `platform:ui_events` через `redis_pubsub_listener`
    (контракт `core.ui_events.dispatcher`).
  - Триггерим `op_messages_send` через REST.
  - Ждём (или НЕ ждём) платформенный push-фрейм:
    * `sync/message/created` — domain push, всегда (для участников канала).
    * `notify/sync/sync_new_message_received` — уведомление, только если
      получатель оффлайн в sync WS, не упомянут и в канале не выставлен mute.
    * `notify/sync/mention_received` — упоминание, всегда (даже при онлайне),
      если только не выставлен mute канала.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as redis_async

from core.config import get_settings
from core.utils.tokens import get_token_service

from tests.sync.api._helpers import create_topic_channel_via_http
from tests.sync.api._realtime_helpers import (
    add_member_via_http,
    connect_ws,
    http_owner,
    send_text_message,
)


def _user_id_from_token(token: str) -> str:
    data = get_token_service().validate_token(token)
    if data is None:
        raise AssertionError("invalid token")
    return data.user_id


async def _ensure_no_presence(user_id: str) -> None:
    """Снимает Redis presence-ключ user'a (на случай хвоста от прошлого теста)."""
    settings = get_settings()
    if not settings.database.redis_url:
        return
    client = redis_async.from_url(settings.database.redis_url)
    try:
        await client.delete(f"sync:ws:presence:{user_id}")
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_notify_user_skipped_when_recipient_has_sync_ws_presence(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    ui_events_listener: PubSubReceive,
) -> None:
    """User2 онлайн в sync WS → `notify/sync/sync_new_message_received` НЕ публикуется."""
    user2_id = _user_id_from_token(sync_auth_token_user2)

    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="presence",
            channel_name="presence_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)

    async with connect_ws(sync_auth_token_user2) as _ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            await send_text_message(
                http, http.headers,
                channel_id=channel_id,
                text=f"presence-skip {unique_id}",
            )
        notify_events = await ui_events_listener(
            "notify/sync/sync_new_message_received",
            user2_id,
            timeout=4.0,
        )

    assert notify_events == [], (
        f"notify-push для user2 не должен прийти при онлайн-presence; got={notify_events!r}"
    )


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_notify_user_delivered_when_recipient_offline(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    ui_events_listener: PubSubReceive,
) -> None:
    """User2 офлайн (нет WS) → ждём `notify/sync/sync_new_message_received` через TaskIQ."""
    user2_id = _user_id_from_token(sync_auth_token_user2)
    await _ensure_no_presence(user2_id)

    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="offline",
            channel_name="offline_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        await send_text_message(
            http, http.headers,
            channel_id=channel_id,
            text=f"offline-deliver {unique_id} {uuid.uuid4().hex[:6]}",
        )

    notify_events = await ui_events_listener(
        "notify/sync/sync_new_message_received",
        user2_id,
        timeout=10.0,
    )
    assert len(notify_events) >= 1, (
        f"ожидалось хотя бы одно notify-событие для user2 при offline-presence; got={notify_events!r}"
    )
    payload = notify_events[0]["payload"]
    assert payload["service"] == "sync"
    assert payload["kind"] == "sync_new_message"
    assert payload.get("data", {}).get("channel_id") == channel_id


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_notify_user_skipped_when_channel_muted(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    ui_events_listener: PubSubReceive,
) -> None:
    """Mute канала у user2 → notify-push не приходит даже при offline-presence."""
    user2_id = _user_id_from_token(sync_auth_token_user2)
    await _ensure_no_presence(user2_id)

    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="mute",
            channel_name="mute_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)

    async with http_owner(sync_auth_token_user2) as http_user2:
        mr = await http_user2.patch(
            f"/sync/api/v1/channels/{channel_id}/notification-settings",
            json={"notifications_muted": True},
        )
        assert mr.status_code == 200, mr.text

    async with http_owner(sync_auth_token) as http:
        await send_text_message(
            http, http.headers,
            channel_id=channel_id,
            text=f"muted {unique_id}",
        )

    notify_events = await ui_events_listener(
        "notify/sync/sync_new_message_received",
        user2_id,
        timeout=4.0,
    )
    assert notify_events == [], (
        f"notify-push для user2 не должен прийти при muted-канале; got={notify_events!r}"
    )


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_mention_notification_delivered_even_with_sync_ws_presence(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    ui_events_listener: PubSubReceive,
) -> None:
    """Mention уведомления НЕ пропускаются по sync presence (см. sync.mdc)."""
    user2_id = _user_id_from_token(sync_auth_token_user2)

    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="ment",
            channel_name="ment_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)

    async with connect_ws(sync_auth_token_user2) as _ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            await send_text_message(
                http, http.headers,
                channel_id=channel_id,
                text=f"hi @{user2_id} {unique_id}",
                mentioned_user_ids=[user2_id],
            )

        notify_events = await ui_events_listener(
            "notify/sync/mention_received",
            user2_id,
            timeout=10.0,
        )

    assert len(notify_events) >= 1, (
        f"ожидалось mention-уведомление user2 при онлайн-presence; got={notify_events!r}"
    )
    payload = notify_events[0]["payload"]
    assert payload["service"] == "sync"
    assert payload["kind"] == "mention"
    assert payload.get("data", {}).get("channel_id") == channel_id

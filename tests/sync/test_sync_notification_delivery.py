"""Доставка платформенных уведомлений sync: TaskIQ deliver_channel_message_notification.

Проверяем ветки (presence, mute), формат notify_user и публикацию в Redis.
Полный Web Push с реальным FCM недоступен в CI: см. tests/core/push/test_push_service.py (mock webpush).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as aioredis

from apps.sync.db.models import SyncChannel, SyncSpace
from apps.sync.realtime.notification_tasks import deliver_channel_message_notification
from core.websocket.manager import REDIS_CHANNEL, notification_manager
from core.websocket.publisher import NotificationType

deliver_fn = deliver_channel_message_notification.original_func


async def _seed_topic_channel(
    space_repo,
    channel_repo,
    company_id: str,
    owner_user_id: str,
    recipient_user_id: str,
) -> tuple[str, str]:
    space_id = uuid.uuid4().hex
    channel_id = uuid.uuid4().hex
    space = SyncSpace(
        space_id=space_id,
        company_id=company_id,
        name="Ns",
        description=None,
        avatar_url=None,
        created_by_user_id=owner_user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        space_id=space_id,
        type="topic",
        name="general",
        is_private=False,
        avatar_url=None,
        created_by_user_id=owner_user_id,
        pinned_message_ids=[],
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel_id, owner_user_id, "owner", company_id=company_id)
    await channel_repo.upsert_member(channel_id, recipient_user_id, "member", company_id=company_id)
    return space_id, channel_id


@pytest.mark.asyncio
async def test_deliver_skips_when_recipient_sync_ws_online(
    sync_db_clean: None,
    space_repo,
    channel_repo,
    company_id: str,
) -> None:
    owner = f"owner_{uuid.uuid4().hex[:8]}"
    recipient = f"recipient_{uuid.uuid4().hex[:8]}"
    _, channel_id = await _seed_topic_channel(
        space_repo, channel_repo, company_id, owner, recipient
    )
    message_id = uuid.uuid4().hex

    with (
        patch(
            "apps.sync.realtime.notification_tasks.is_user_sync_ws_online",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_online,
        patch(
            "apps.sync.realtime.notification_tasks.notify_user",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        await deliver_fn(
            recipient_user_id=recipient,
            channel_id=channel_id,
            company_id=company_id,
            message_id=message_id,
            sender_display_name="Sender",
            notification_title="Ch",
            body_preview="Hi",
        )

    mock_online.assert_awaited_once()
    mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_skips_when_channel_muted(
    sync_db_clean: None,
    space_repo,
    channel_repo,
    company_id: str,
) -> None:
    owner = f"owner_{uuid.uuid4().hex[:8]}"
    recipient = f"recipient_{uuid.uuid4().hex[:8]}"
    _, channel_id = await _seed_topic_channel(
        space_repo, channel_repo, company_id, owner, recipient
    )
    await channel_repo.set_member_notifications_muted(
        channel_id, recipient, True, company_id=company_id
    )
    message_id = uuid.uuid4().hex

    with (
        patch(
            "apps.sync.realtime.notification_tasks.is_user_sync_ws_online",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "apps.sync.realtime.notification_tasks.notify_user",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        await deliver_fn(
            recipient_user_id=recipient,
            channel_id=channel_id,
            company_id=company_id,
            message_id=message_id,
            sender_display_name="Sender",
            notification_title="Ch",
            body_preview="Hi",
        )

    mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_calls_notify_user_with_sync_new_message_payload(
    sync_db_clean: None,
    space_repo,
    channel_repo,
    company_id: str,
) -> None:
    owner = f"owner_{uuid.uuid4().hex[:8]}"
    recipient = f"recipient_{uuid.uuid4().hex[:8]}"
    _, channel_id = await _seed_topic_channel(
        space_repo, channel_repo, company_id, owner, recipient
    )
    message_id = uuid.uuid4().hex

    with (
        patch(
            "apps.sync.realtime.notification_tasks.is_user_sync_ws_online",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "apps.sync.realtime.notification_tasks.notify_user",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        await deliver_fn(
            recipient_user_id=recipient,
            channel_id=channel_id,
            company_id=company_id,
            message_id=message_id,
            sender_display_name="Alice",
            notification_title="Team",
            body_preview="Hello world",
        )

    mock_notify.assert_awaited_once()
    call_args = mock_notify.call_args
    assert call_args[0][0] == recipient
    notif = call_args[0][1]
    assert notif.type == NotificationType.SYNC_NEW_MESSAGE
    assert notif.title == "Team"
    assert "Alice" in notif.message and "Hello world" in notif.message
    assert notif.service == "sync"
    assert notif.action_url == f"/sync?channel={channel_id}"
    assert notif.data["channel_id"] == channel_id
    assert notif.data["message_id"] == message_id


@pytest.mark.asyncio
async def test_deliver_notify_user_publishes_to_redis(
    sync_db_clean: None,
    space_repo,
    channel_repo,
    company_id: str,
) -> None:
    redis_url = os.environ.get("DATABASE__REDIS_URL")
    if not redis_url:
        pytest.skip("DATABASE__REDIS_URL не задан")

    owner = f"owner_{uuid.uuid4().hex[:8]}"
    recipient = f"recipient_{uuid.uuid4().hex[:8]}"
    _, channel_id = await _seed_topic_channel(
        space_repo, channel_repo, company_id, owner, recipient
    )
    message_id = uuid.uuid4().hex

    r = aioredis.from_url(redis_url)
    notification_manager._redis_client = r
    sub = aioredis.from_url(redis_url)
    pubsub = sub.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    try:
        await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

        with patch(
            "apps.sync.realtime.notification_tasks.is_user_sync_ws_online",
            new_callable=AsyncMock,
            return_value=False,
        ):
            from core.websocket.publisher import notify_user as real_notify

            await deliver_fn(
                recipient_user_id=recipient,
                channel_id=channel_id,
                company_id=company_id,
                message_id=message_id,
                sender_display_name="Bob",
                notification_title="Chan",
                body_preview="Text",
            )

        raw = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=5.0)
        assert raw is not None
        assert raw["type"] == "message"
        envelope = json.loads(raw["data"])
        assert envelope["user_id"] == recipient
        assert envelope["notification"]["type"] == NotificationType.SYNC_NEW_MESSAGE.value
        assert envelope["notification"]["data"]["channel_id"] == channel_id
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL)
        await pubsub.aclose()
        await sub.aclose()
        notification_manager._redis_client = None
        await r.aclose()


@pytest.mark.asyncio
@patch("core.push.service.webpush")
async def test_deliver_triggers_webpush_when_vapid_configured(
    mock_webpush,
    sync_db_clean: None,
    space_repo,
    channel_repo,
    company_id: str,
    push_repository,
    vapid_keys,
) -> None:
    from unittest.mock import MagicMock

    from core.push.service import init_web_push_service
    from core.websocket.publisher import notify_user as real_notify_user

    redis_url = os.environ.get("DATABASE__REDIS_URL")
    if not redis_url:
        pytest.skip("DATABASE__REDIS_URL не задан")

    mock_webpush.return_value = MagicMock(status_code=201)

    init_web_push_service(
        vapid_private_key=vapid_keys["private_key"],
        vapid_public_key=vapid_keys["public_key"],
        vapid_email=vapid_keys["email"],
    )

    owner = f"owner_{uuid.uuid4().hex[:8]}"
    recipient = f"recipient_{uuid.uuid4().hex[:8]}"
    _, channel_id = await _seed_topic_channel(
        space_repo, channel_repo, company_id, owner, recipient
    )
    message_id = uuid.uuid4().hex
    endpoint = f"https://fcm.googleapis.com/sync-deliver-{uuid.uuid4().hex}"
    await push_repository.upsert_subscription(
        user_id=recipient,
        endpoint=endpoint,
        keys={"p256dh": "k", "auth": "a"},
        platform="desktop",
    )

    r = aioredis.from_url(redis_url)
    notification_manager._redis_client = r
    try:
        with patch(
            "apps.sync.realtime.notification_tasks.is_user_sync_ws_online",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch(
                "apps.sync.realtime.notification_tasks.notify_user",
                wraps=real_notify_user,
            ):
                await deliver_fn(
                    recipient_user_id=recipient,
                    channel_id=channel_id,
                    company_id=company_id,
                    message_id=message_id,
                    sender_display_name="U",
                    notification_title="T",
                    body_preview="B",
                )

        mock_webpush.assert_called()
    finally:
        notification_manager._redis_client = None
        await r.aclose()
        await push_repository.delete_subscription(recipient, endpoint)

"""TaskIQ: доставка платформенных уведомлений о сообщениях sync (notify_user, задел под мобильный push)."""

from __future__ import annotations

from apps.sync.realtime.broker import broker
from apps.sync.container import get_sync_container
from apps.sync.ws_presence import is_user_sync_ws_online
from core.config import get_settings
from core.logging import get_logger
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


@broker.task
async def deliver_channel_message_notification(
    recipient_user_id: str,
    channel_id: str,
    company_id: str,
    message_id: str,
    sender_display_name: str,
    notification_title: str,
    body_preview: str,
) -> None:
    settings = get_settings()
    if not settings.database.redis_url:
        raise ValueError("database.redis_url не задан")
    if await is_user_sync_ws_online(settings.database.redis_url, recipient_user_id):
        logger.debug(
            "sync notify skipped: user has sync ws: user=%s channel=%s",
            recipient_user_id,
            channel_id,
        )
        return

    container = get_sync_container()
    muted = await container.channel_repository.get_member_notifications_muted(
        channel_id,
        recipient_user_id,
        company_id=company_id,
    )
    if muted:
        logger.debug(
            "sync notify skipped: muted: user=%s channel=%s",
            recipient_user_id,
            channel_id,
        )
        return

    line = f"{sender_display_name}: {body_preview}".strip()
    if len(line) > 500:
        line = line[:499] + "…"

    action_url = f"/sync?channel={channel_id}"
    await notify_user(
        recipient_user_id,
        Notification(
            type=NotificationType.SYNC_NEW_MESSAGE,
            title=notification_title,
            message=line,
            service="sync",
            priority="normal",
            action_url=action_url,
            data={
                "channel_id": channel_id,
                "message_id": message_id,
            },
        ),
    )

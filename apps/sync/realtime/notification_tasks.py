"""TaskIQ: доставка платформенных уведомлений о сообщениях sync (notify_user, задел под мобильный push).

Без broker retry: повторная доставка может дублировать toast/пуш без отдельной идемпотентности по message_id.
"""

from __future__ import annotations

from apps.sync.models.channel_member import SyncChannelMember
from apps.sync.realtime.task_names import (
    DELIVER_CHANNEL_MESSAGE_NOTIFICATION,
    DELIVER_SYNC_MENTION_NOTIFICATION,
)
from core.logging import get_logger
from core.realtime.presence import is_user_connected
from core.tasks import platform_task
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


@platform_task(DELIVER_CHANNEL_MESSAGE_NOTIFICATION)
async def deliver_channel_message_notification(
    recipient_user_id: str,
    channel_id: str,
    company_id: str,
    message_id: str,
    sender_display_name: str,
    notification_title: str,
    body_preview: str,
) -> None:
    if await is_user_connected(recipient_user_id, company_id=company_id):
        logger.debug("sync.notify.skipped.user.connected", user=recipient_user_id, channel=channel_id)
        return

    muted = await SyncChannelMember.channel_member_notifications_muted(
        channel_id,
        recipient_user_id,
        company_id=company_id,
    )
    if muted:
        logger.debug("sync.notify.skipped.muted.user", user=recipient_user_id, channel=channel_id)
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


@platform_task(DELIVER_SYNC_MENTION_NOTIFICATION)
async def deliver_sync_mention_notification(
    recipient_user_id: str,
    channel_id: str,
    company_id: str,
    message_id: str,
    sender_display_name: str,
    notification_title: str,
    body_preview: str,
) -> None:
    """Упоминание: без проверки Centrifugo presence, только mute канала."""
    muted = await SyncChannelMember.channel_member_notifications_muted(
        channel_id,
        recipient_user_id,
        company_id=company_id,
    )
    if muted:
        logger.debug("sync.mention.notify.skipped.muted", user=recipient_user_id, channel=channel_id)
        return

    line = f"{sender_display_name}: {body_preview}".strip()
    if len(line) > 500:
        line = line[:499] + "…"

    action_url = f"/sync?channel={channel_id}"
    await notify_user(
        recipient_user_id,
        Notification(
            type=NotificationType.MENTION,
            title=notification_title,
            message=line,
            service="sync",
            priority="high",
            action_url=action_url,
            data={
                "channel_id": channel_id,
                "message_id": message_id,
            },
        ),
    )

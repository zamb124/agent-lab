"""
Доставка офлайн-push: Web Push (VAPID) и APNs по типу подписки.
"""

from __future__ import annotations

from typing import Any

from core.config import get_settings
from core.logging import get_logger
from core.push.apns_service import get_apns_push_service
from core.push.models import PushSubscription
from core.push.repository import PushSubscriptionRepository
from core.push.service import get_web_push_service

logger = get_logger(__name__)


def _is_apns_subscription(subscription: PushSubscription) -> bool:
    return subscription.endpoint.startswith("apns:")


async def deliver_offline_push(
    user_id: str,
    *,
    title: str,
    message: str,
    action_url: str | None,
    tag: str,
    priority: str,
    data: dict[str, Any],
) -> list[str]:
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")
    db_url = settings.database.shared_url

    repo = PushSubscriptionRepository(db_url=db_url)
    subscriptions = await repo.get_user_subscriptions(user_id)
    if not subscriptions:
        return []

    web_subs = [s for s in subscriptions if not _is_apns_subscription(s)]
    apns_subs = [s for s in subscriptions if _is_apns_subscription(s)]

    expired_endpoints: list[str] = []

    push_service = get_web_push_service()
    if web_subs and push_service and push_service.is_configured:
        expired_endpoints.extend(
            await push_service.send_to_user(
                subscriptions=web_subs,
                title=title,
                message=message,
                url=action_url,
                tag=tag,
                priority=priority,
                data=data,
            )
        )

    apns_service = get_apns_push_service()
    if apns_subs and apns_service and apns_service.is_configured:
        for sub in apns_subs:
            token_hex = sub.endpoint.removeprefix("apns:")
            delivered, drop = await apns_service.send_alert(
                device_token_hex=token_hex,
                title=title,
                body=message,
                url=action_url,
                tag=tag,
                extra=data,
            )
            if not delivered and drop:
                expired_endpoints.append(sub.endpoint)
            elif not delivered:
                logger.warning(
                    "APNs: пропуск удаления подписки после временной ошибки endpoint=%s",
                    sub.endpoint[:32],
                )

    for endpoint in expired_endpoints:
        await repo.delete_by_endpoint(endpoint)

    if expired_endpoints:
        logger.info("Удалено %s истёкших или невалидных push подписок", len(expired_endpoints))

    return expired_endpoints

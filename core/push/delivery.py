"""
Доставка офлайн-push: Web Push (VAPID), APNs (iOS) и FCM (Android) по типу подписки.
"""

from __future__ import annotations

from core.config import get_settings
from core.db.models import PushSubscription
from core.logging import get_logger
from core.push.apns_service import get_apns_push_service
from core.push.fcm_service import get_fcm_push_service
from core.push.repository import PushSubscriptionRepository
from core.push.service import get_web_push_service
from core.types import JsonObject

logger = get_logger(__name__)


def _is_apns_subscription(subscription: PushSubscription) -> bool:
    return subscription.endpoint.startswith("apns:")


def _is_fcm_subscription(subscription: PushSubscription) -> bool:
    return subscription.endpoint.startswith("fcm:")


async def deliver_offline_push(
    user_id: str,
    *,
    title: str,
    message: str,
    action_url: str | None,
    tag: str,
    priority: str,
    data: JsonObject,
) -> list[str]:
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")

    push_service = get_web_push_service()
    apns_service = get_apns_push_service()
    fcm_service = get_fcm_push_service()
    if not (
        (push_service and push_service.is_configured)
        or (apns_service and apns_service.is_configured)
        or (fcm_service and fcm_service.is_configured)
    ):
        return []

    db_url = settings.database.shared_url

    repo = PushSubscriptionRepository(db_url=db_url)
    subscriptions = await repo.get_user_subscriptions(user_id)
    if not subscriptions:
        return []

    web_subs = [
        s for s in subscriptions
        if not _is_apns_subscription(s) and not _is_fcm_subscription(s)
    ]
    apns_subs = [s for s in subscriptions if _is_apns_subscription(s)]
    fcm_subs = [s for s in subscriptions if _is_fcm_subscription(s)]

    expired_endpoints: list[str] = []

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

    if fcm_subs and fcm_service and fcm_service.is_configured:
        for sub in fcm_subs:
            token = sub.endpoint.removeprefix("fcm:")
            delivered, drop = await fcm_service.send_alert(
                registration_token=token,
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
                    "FCM: пропуск удаления подписки после временной ошибки endpoint=%s",
                    sub.endpoint[:32],
                )

    for endpoint in expired_endpoints:
        _ = await repo.delete_by_endpoint(endpoint)

    if expired_endpoints:
        logger.info("Удалено %s истёкших или невалидных push подписок", len(expired_endpoints))

    return expired_endpoints

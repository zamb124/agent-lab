"""
Web Push Service для отправки push-уведомлений
"""
import json
from typing import TypeAlias

from pywebpush import WebPushException, webpush

from core.db.models import PushSubscription
from core.logging import get_logger
from core.types import JsonObject, PushSubscriptionKeys

logger = get_logger(__name__)

WebPushKeys: TypeAlias = dict[str, str | bytes]
WebPushSubscriptionInfo: TypeAlias = dict[str, str | bytes | WebPushKeys]


class WebPushService:
    """Сервис отправки Web Push уведомлений"""

    def __init__(
        self,
        vapid_private_key: str,
        vapid_public_key: str,
        vapid_email: str,
    ) -> None:
        self.vapid_private_key: str = vapid_private_key
        self.vapid_public_key: str = vapid_public_key
        self.vapid_claims: dict[str, str | int] = {"sub": f"mailto:{vapid_email}"}
        self._initialized: bool = bool(vapid_private_key and vapid_public_key)

    @property
    def is_configured(self) -> bool:
        """Проверка конфигурации VAPID"""
        return self._initialized

    async def send_push(
        self,
        subscription: PushSubscription,
        title: str,
        message: str,
        url: str | None = None,
        tag: str | None = None,
        priority: str = "normal",
        data: JsonObject | None = None,
    ) -> bool:
        """
        Отправить push-уведомление на устройство

        Возвращает:
            True если успешно, False если ошибка или подписка истекла
        """
        if not self._initialized:
            logger.warning("WebPushService не настроен - пропускаем отправку")
            return False

        payload: JsonObject = {
            "title": title,
            "message": message,
            "url": url or "/",
            "tag": tag or "notification",
            "priority": priority,
            "data": data if data is not None else {},
        }

        try:
            subscription_keys: PushSubscriptionKeys = subscription.keys
            keys: WebPushKeys = {
                "p256dh": subscription_keys["p256dh"],
                "auth": subscription_keys["auth"],
            }
            subscription_info: WebPushSubscriptionInfo = {
                "endpoint": subscription.endpoint,
                "keys": keys,
            }
            _ = webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims,
            )
            logger.debug(f"Push отправлен: {title} -> {subscription.platform}")
            return True

        except WebPushException as e:
            if e.response and e.response.status_code == 410:
                # 410 Gone — подписка истекла, нужно удалить
                logger.info(f"Push подписка истекла: {subscription.endpoint[:50]}...")
                return False
            elif e.response and e.response.status_code == 404:
                # 404 Not Found — подписка не существует
                logger.info(f"Push подписка не найдена: {subscription.endpoint[:50]}...")
                return False
            else:
                logger.error(f"Ошибка отправки push: {e}")
                return False

    async def send_to_user(
        self,
        subscriptions: list[PushSubscription],
        title: str,
        message: str,
        url: str | None = None,
        tag: str | None = None,
        priority: str = "normal",
        data: JsonObject | None = None,
    ) -> list[str]:
        """
        Отправить push на все устройства пользователя

        Возвращает:
            Список endpoints с истекшими подписками (для удаления)
        """
        expired_endpoints: list[str] = []

        for subscription in subscriptions:
            if subscription.endpoint.startswith("apns:"):
                continue
            success = await self.send_push(
                subscription=subscription,
                title=title,
                message=message,
                url=url,
                tag=tag,
                priority=priority,
                data=data,
            )
            if not success:
                expired_endpoints.append(subscription.endpoint)

        return expired_endpoints


# Глобальный инстанс
_web_push_service: WebPushService | None = None


def init_web_push_service(
    vapid_private_key: str,
    vapid_public_key: str,
    vapid_email: str,
) -> WebPushService:
    """Инициализация глобального сервиса"""
    global _web_push_service
    _web_push_service = WebPushService(
        vapid_private_key=vapid_private_key,
        vapid_public_key=vapid_public_key,
        vapid_email=vapid_email,
    )
    return _web_push_service


def get_web_push_service() -> WebPushService | None:
    """Получить глобальный сервис"""
    return _web_push_service

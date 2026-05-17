"""
Web Push Service для отправки push-уведомлений
"""
import json
from typing import Any, List, Optional

from pywebpush import WebPushException, webpush

from core.logging import get_logger
from core.push.models import PushSubscription

logger = get_logger(__name__)


class WebPushService:
    """Сервис отправки Web Push уведомлений"""

    def __init__(
        self,
        vapid_private_key: str,
        vapid_public_key: str,
        vapid_email: str
    ):
        self.vapid_private_key = vapid_private_key
        self.vapid_public_key = vapid_public_key
        self.vapid_claims: dict[str, str | int] = {"sub": f"mailto:{vapid_email}"}
        self._initialized = bool(vapid_private_key and vapid_public_key)

    @property
    def is_configured(self) -> bool:
        """Проверка конфигурации VAPID"""
        return self._initialized

    async def send_push(
        self,
        subscription: PushSubscription,
        title: str,
        message: str,
        url: Optional[str] = None,
        tag: Optional[str] = None,
        priority: str = "normal",
        data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Отправить push-уведомление на устройство

        Returns:
            True если успешно, False если ошибка или подписка истекла
        """
        if not self._initialized:
            logger.warning("WebPushService не настроен - пропускаем отправку")
            return False

        payload = {
            "title": title,
            "message": message,
            "url": url or "/",
            "tag": tag or "notification",
            "priority": priority,
            "data": data or {}
        }

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": subscription.keys
                },
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims
            )
            logger.debug(f"Push отправлен: {title} -> {subscription.platform}")
            return True

        except WebPushException as e:
            if e.response and e.response.status_code == 410:
                # Gone - подписка истекла, нужно удалить
                logger.info(f"Push подписка истекла: {subscription.endpoint[:50]}...")
                return False
            elif e.response and e.response.status_code == 404:
                # Not Found - подписка не существует
                logger.info(f"Push подписка не найдена: {subscription.endpoint[:50]}...")
                return False
            else:
                logger.error(f"Ошибка отправки push: {e}")
                return False

    async def send_to_user(
        self,
        subscriptions: List[PushSubscription],
        title: str,
        message: str,
        url: Optional[str] = None,
        tag: Optional[str] = None,
        priority: str = "normal",
        data: dict[str, Any] | None = None,
    ) -> List[str]:
        """
        Отправить push на все устройства пользователя

        Returns:
            Список endpoints с истекшими подписками (для удаления)
        """
        expired_endpoints = []

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
                data=data
            )
            if not success:
                expired_endpoints.append(subscription.endpoint)

        return expired_endpoints


# Глобальный инстанс
_web_push_service: Optional[WebPushService] = None


def init_web_push_service(
    vapid_private_key: str,
    vapid_public_key: str,
    vapid_email: str
) -> WebPushService:
    """Инициализация глобального сервиса"""
    global _web_push_service
    _web_push_service = WebPushService(
        vapid_private_key=vapid_private_key,
        vapid_public_key=vapid_public_key,
        vapid_email=vapid_email
    )
    return _web_push_service


def get_web_push_service() -> Optional[WebPushService]:
    """Получить глобальный сервис"""
    return _web_push_service


# Алиас для обратной совместимости
web_push_service = None

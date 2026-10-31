"""NotificationService — доставка уведомлений о заказах владельцу магазина.

MVP-канал — Telegram-чат, привязанный к магазину (``Shop.telegram_chat_id``),
бот платформы ``settings.telegram_bot_token``. Ошибка доставки не откатывает
заказ: задача ретраится TaskIQ, финальный промах фиксируется в логе.
"""

from __future__ import annotations

from apps.shop.config import ShopSettings
from apps.shop.models import Shop, ShopOrder, ShopOrderItem
from core.errors.boundary import PlatformUnavailableError
from core.http.client import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)

_STATUS_LABEL: dict[str, str] = {
    "new": "Новый",
    "accepted": "Принят",
    "preparing": "Готовится",
    "delivering": "В доставке",
    "done": "Выполнен",
    "cancelled": "Отменён",
}

_TELEGRAM_API_BASE = "https://api.telegram.org"


class NotificationService:
    """Уведомления магазина: Telegram-сообщение о новом заказе и смене статуса."""

    def __init__(self, settings: ShopSettings) -> None:
        self._settings = settings

    async def notify_order(self, shop_order_id: str) -> bool:
        """Уведомление о заказе; False — чат не привязан к магазину."""
        order = await ShopOrder.get_by_id(shop_order_id)
        if order is None:
            return False
        shop = await Shop.get_by_id(order.shop_id)
        if shop is None or not shop.telegram_chat_id:
            return False
        token = self._settings.telegram_bot_token
        if not token:
            raise PlatformUnavailableError(
                "Telegram-бот shop не настроен (telegram_bot_token)",
                error_code="shop_telegram_unconfigured",
            )
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        lines = [
            f"Заказ #{order.public_code} — {_STATUS_LABEL[order.status.value]}",
            "",
            *[
                f"• {i.name_snapshot} × {i.qty} — {i.price_minor * i.qty // 100} ₽"
                for i in items
            ],
            "",
            f"Итого: {order.total_minor // 100} ₽",
            f"Клиент: {order.customer_name} {order.customer_phone}",
        ]
        if order.delivery_type.value == "delivery":
            lines.append(f"Доставка: {order.address}")
        if order.comment:
            lines.append(f"Комментарий: {order.comment}")
        try:
            response = await get_httpx_client().post(
                f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage",
                json={
                    "chat_id": shop.telegram_chat_id,
                    "text": "\n".join(lines),
                },
            )
        except Exception as exc:
            logger.warning(
                "shop_notify_order_failed",
                extra={"shop_order_id": shop_order_id, "error": str(exc)},
            )
            raise PlatformUnavailableError(
                "Telegram API недоступен", error_code="shop_telegram_unavailable"
            ) from exc
        if response.status_code >= 400:
            logger.warning(
                "shop_notify_order_rejected",
                extra={
                    "shop_order_id": shop_order_id,
                    "status_code": response.status_code,
                },
            )
            return False
        return True

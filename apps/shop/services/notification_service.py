"""NotificationService — Telegram-канал магазина для уведомлений о заказах.

У каждой витрины — свой бот (BotFather → токен в настройках магазина):
директор подключает его одной кнопкой, сервис ставит webhook на публичный
endpoint витрины с ``secret_token`` и бот привязывает чат по ``/start``.
Ошибка доставки не откатывает заказ: задача ретраится TaskIQ, финальный
промах фиксируется в логе.
"""

from __future__ import annotations

import secrets

from apps.shop.config import ShopSettings
from apps.shop.models import Shop, ShopOrder, ShopOrderItem, order_status_label
from core.errors.boundary import (
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.http.client import get_httpx_client
from core.logging import get_logger
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)

def order_notify_text(order: ShopOrder, items: list[ShopOrderItem]) -> str:
    """Текст уведомления о заказе для Telegram-бота магазина.

    Способ выдачи одной строкой: адрес для delivery, стол для onsite;
    pickup без дополнительной строки — гость сам придёт.
    """
    label = order_status_label(order.status, order.delivery_type)
    lines = [
        f"Заказ #{order.public_code} — {label}",
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
    elif order.delivery_type.value == "onsite":
        lines.append(f"В заведении: {order.table_label}")
    if order.comment:
        lines.append(f"Комментарий: {order.comment}")
    return "\n".join(lines)


class NotificationService:
    """Telegram магазина: подключение бота, webhook и уведомления о заказах."""

    def __init__(self, settings: ShopSettings) -> None:
        self._settings: ShopSettings = settings

    async def _bot_call(
        self, token: str, method: str, payload: JsonObject
    ) -> JsonObject:
        """Вызов Bot API для конкретного бота магазина."""
        try:
            response = await get_httpx_client().post(
                f"{self._settings.telegram.api_base}/bot{token}/{method}",
                json=dict(payload),
            )
        except Exception as exc:
            raise PlatformUnavailableError(
                "Telegram API unavailable", error_code="shop_telegram_unavailable"
            ) from exc
        body = parse_json_object(response.text, "Telegram response")
        if response.status_code >= 400 or body.get("ok") is not True:
            logger.warning(
                "shop_telegram_call_failed",
                extra={"method": method, "status_code": response.status_code},
            )
            raise PlatformUnavailableError(
                "Telegram rejected the request", error_code="shop_telegram_rejected"
            )
        try:
            return require_json_object(body.get("result"), "Telegram result")
        except ValueError as exc:
            raise PlatformUnavailableError(
                "Telegram rejected the request", error_code="shop_telegram_rejected"
            ) from exc

    def _webhook_url(self, shop: Shop) -> str:
        return (
            f"https://{shop.slug}.{self._settings.storefront_domain_suffix}"
            f"/shop/api/v1/public/telegram/webhook/{shop.shop_id}"
        )

    async def connect_telegram(
        self, company_id: str, shop_id: str, bot_token: str
    ) -> Shop:
        """Валидировать токен через getMe и поднять webhook бота магазина."""
        shop = await Shop.get_by_id(shop_id)
        if shop is None or str(shop.company_id) != company_id:
            raise PlatformNotFoundError(
                "Shop not found", error_code="shop_not_found"
            )
        me = await self._bot_call(bot_token, "getMe", JsonObject())
        if not isinstance(me.get("id"), int):
            raise PlatformUnavailableError(
                "Unexpected Telegram getMe response",
                error_code="shop_telegram_rejected",
            )
        secret = secrets.token_urlsafe(24)
        _ = await self._bot_call(
            bot_token,
            "setWebhook",
            JsonObject(
                {
                    "url": self._webhook_url(shop),
                    "secret_token": secret,
                    "allowed_updates": ["message"],
                    "drop_pending_updates": True,
                }
            ),
        )
        shop.telegram_bot_token = bot_token
        shop.telegram_webhook_secret = secret
        _ = await shop.save()
        logger.info(
            "shop_telegram_connected",
            extra={"shop_id": shop_id, "bot": me.get("username")},
        )
        return shop

    async def disconnect_telegram(self, company_id: str, shop_id: str) -> Shop:
        """Снять webhook и отвязать чат: уведомления магазину останавливаются."""
        shop = await Shop.get_by_id(shop_id)
        if shop is None or str(shop.company_id) != company_id:
            raise PlatformNotFoundError(
                "Shop not found", error_code="shop_not_found"
            )
        if shop.telegram_bot_token:
            try:
                _ = await self._bot_call(
                    shop.telegram_bot_token,
                    "deleteWebhook",
                    JsonObject({"drop_pending_updates": True}),
                )
            except (PlatformUnavailableError, PlatformUnavailableError):
                logger.warning(
                    "shop_telegram_delete_webhook_failed",
                    extra={"shop_id": shop_id},
                )
        shop.telegram_bot_token = None
        shop.telegram_webhook_secret = None
        shop.telegram_chat_id = None
        _ = await shop.save()
        return shop

    async def handle_telegram_update(
        self, shop_id: str, secret: str | None, update: JsonObject
    ) -> None:
        """Входящий update бота магазина: ``/start`` привязывает чат уведомлений.

        Секрет сверяется до любой работы — webhook публичен, но без
        ``X-Telegram-Bot-Api-Secret-Token`` update отклоняется.
        """
        shop = await Shop.get_by_id(shop_id)
        if (
            shop is None
            or not shop.telegram_webhook_secret
            or shop.telegram_bot_token is None
            or secret != shop.telegram_webhook_secret
        ):
            raise PlatformNotFoundError(
                "Webhook not found", error_code="telegram_webhook_not_found"
            )
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("id") is None:
            return
        chat_id = str(chat["id"])
        text = message.get("text")
        if isinstance(text, str) and text.startswith("/start"):
            shop.telegram_chat_id = chat_id
            _ = await shop.save()
            try:
                _ = await self._bot_call(
                    shop.telegram_bot_token,
                    "sendMessage",
                    JsonObject(
                        {
                            "chat_id": chat_id,
                            "text": (
                                "Уведомления магазина подключены. "
                                "Сюда будут приходить новые заказы."
                            ),
                        }
                    ),
                )
            except PlatformUnavailableError:
                logger.warning(
                    "shop_telegram_confirm_failed",
                    extra={"shop_id": shop_id, "chat_id": chat_id},
                )
            logger.info(
                "shop_telegram_chat_bound",
                extra={"shop_id": shop_id, "chat_id": chat_id},
            )

    async def notify_order(self, shop_order_id: str) -> bool:
        """Уведомление о заказе; False — бот или чат не подключены."""
        order = await ShopOrder.get_by_id(shop_order_id)
        if order is None:
            return False
        shop = await Shop.get_by_id(order.shop_id)
        if (
            shop is None
            or not shop.telegram_chat_id
            or not shop.telegram_bot_token
        ):
            return False
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        text = order_notify_text(order, items)
        try:
            _ = await self._bot_call(
                shop.telegram_bot_token,
                "sendMessage",
                JsonObject(
                    {
                        "chat_id": shop.telegram_chat_id,
                        "text": text,
                    }
                ),
            )
        except (PlatformUnavailableError, PlatformUnavailableError) as exc:
            logger.warning(
                "shop_notify_order_failed",
                extra={"shop_order_id": shop_order_id, "error": str(exc)},
            )
            return False
        return True

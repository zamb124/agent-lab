"""События shop на шине `platform:events`.

Доменные факты витрин и заказов публикуются только здесь: по ним
админ-панель обновляет доску заказов, а подписчики платформы реагируют
на публикацию магазина.
"""

from __future__ import annotations

from pydantic import BaseModel

from apps.shop.models.enums import ShopDeliveryType, ShopOrderStatus, ShopStatus
from core.events import (
    publish_domain_event,
    publish_event_to_company,
    register_platform_event,
)
from core.types import JsonObject

SHOP_SHOP_CREATED = "shop/shop/created"
SHOP_SHOP_UPDATED = "shop/shop/updated"
SHOP_SHOP_PUBLISHED = "shop/shop/published"
SHOP_CATALOG_CHANGED = "shop/catalog/changed"
SHOP_ORDER_CREATED = "shop/order/created"
SHOP_ORDER_STATUS_CHANGED = "shop/order/status_changed"


class ShopShopEventPayload(BaseModel):
    """Payload событий жизненного цикла витрины."""

    shop_id: str
    slug: str
    status: ShopStatus


class ShopCatalogChangedEventPayload(BaseModel):
    """Payload `shop/catalog/changed` — снапшот витрины надо пересобрать."""

    shop_id: str
    slug: str


class ShopOrderEventPayload(BaseModel):
    """Payload событий заказа: в пуш уходит публичная форма без PII."""

    shop_id: str
    shop_order_id: str
    public_code: str
    status: ShopOrderStatus
    status_label: str = ""
    delivery_type: ShopDeliveryType = ShopDeliveryType.PICKUP
    total_minor: int
    currency: str


register_platform_event(
    SHOP_SHOP_CREATED,
    ShopShopEventPayload,
    description="Создан магазин shop.",
)
register_platform_event(
    SHOP_SHOP_UPDATED,
    ShopShopEventPayload,
    description="Изменены настройки магазина shop.",
)
register_platform_event(
    SHOP_SHOP_PUBLISHED,
    ShopShopEventPayload,
    description="Магазин shop опубликован: витрина доступна публично.",
)
register_platform_event(
    SHOP_CATALOG_CHANGED,
    ShopCatalogChangedEventPayload,
    description="Изменился каталог магазина shop: снапшот витрины инвалидирован.",
)
register_platform_event(
    SHOP_ORDER_CREATED,
    ShopOrderEventPayload,
    description="Создан заказ в витрине shop.",
)
register_platform_event(
    SHOP_ORDER_STATUS_CHANGED,
    ShopOrderEventPayload,
    description="Изменён статус заказа shop.",
)


async def publish_shop_event(
    event_type: str, shop_id: str, slug: str, status: ShopStatus, company_id: str
) -> None:
    payload = ShopShopEventPayload(shop_id=shop_id, slug=slug, status=status)
    await publish_event_to_company(
        company_id=company_id,
        type=event_type,
        payload=payload.model_dump(mode="json"),
    )


async def publish_shop_ai_call_finished(
    *,
    company_id: str,
    call_id: str,
    shop_id: str,
    verb: str,
    status: str,
    result: JsonObject | None = None,
    error: str | None = None,
) -> None:
    """Терминал AI-вызова: результат/ошибка по ``call_id`` — UI достраивает ответ op'а."""
    await publish_event_to_company(
        company_id=company_id,
        type="shop/ai_call/finished",
        payload={
            "call_id": call_id,
            "shop_id": shop_id,
            "verb": verb,
            "status": status,
            "result": result,
            "error": error,
        },
    )


async def publish_shop_catalog_changed(
    shop_id: str, slug: str, company_id: str
) -> None:
    """Факт смены каталога: flows-триггеры + UI-рефреш списка товаров.

    Доставляется в компанию (вкладки и batch-мутации с сервера видят
    изменения каталога) и как доменное событие для flows-триггеров.
    """
    dumped = ShopCatalogChangedEventPayload(shop_id=shop_id, slug=slug).model_dump(
        mode="json"
    )
    await publish_event_to_company(
        company_id=company_id,
        type=SHOP_CATALOG_CHANGED,
        payload=dumped,
    )
    await publish_domain_event(
        type=SHOP_CATALOG_CHANGED,
        company_id=company_id,
        payload=dumped,
    )


async def publish_shop_order_event(
    event_type: str,
    shop_id: str,
    shop_order_id: str,
    public_code: str,
    status: ShopOrderStatus,
    status_label: str,
    delivery_type: ShopDeliveryType,
    total_minor: int,
    currency: str,
    company_id: str,
) -> None:
    payload = ShopOrderEventPayload(
        shop_id=shop_id,
        shop_order_id=shop_order_id,
        public_code=public_code,
        status=status,
        status_label=status_label,
        delivery_type=delivery_type,
        total_minor=total_minor,
        currency=currency,
    )
    await publish_event_to_company(
        company_id=company_id,
        type=event_type,
        payload=payload.model_dump(mode="json"),
    )


__all__ = [
    "SHOP_CATALOG_CHANGED",
    "SHOP_ORDER_CREATED",
    "SHOP_ORDER_STATUS_CHANGED",
    "SHOP_SHOP_CREATED",
    "SHOP_SHOP_PUBLISHED",
    "SHOP_SHOP_UPDATED",
    "ShopCatalogChangedEventPayload",
    "ShopOrderEventPayload",
    "ShopShopEventPayload",
    "publish_shop_catalog_changed",
    "publish_shop_event",
    "publish_shop_order_event",
]

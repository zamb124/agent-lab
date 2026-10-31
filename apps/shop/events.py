"""События shop на шине `platform:events`.

Доменные факты витрин и заказов публикуются только здесь: по ним
админ-панель обновляет доску заказов, а подписчики платформы реагируют
на публикацию магазина.
"""

from __future__ import annotations

from pydantic import BaseModel

from apps.shop.models.enums import ShopOrderStatus, ShopStatus
from core.events import (
    publish_domain_event,
    publish_event_to_company,
    register_platform_event,
)

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


async def publish_shop_catalog_changed(
    shop_id: str, slug: str, company_id: str
) -> None:
    """Доменный факт для flows-триггеров; UI меню и так знает свои мутации."""
    payload = ShopCatalogChangedEventPayload(shop_id=shop_id, slug=slug)
    await publish_domain_event(
        type=SHOP_CATALOG_CHANGED,
        company_id=company_id,
        payload=payload.model_dump(mode="json"),
    )


async def publish_shop_order_event(
    event_type: str,
    shop_id: str,
    shop_order_id: str,
    public_code: str,
    status: ShopOrderStatus,
    total_minor: int,
    currency: str,
    company_id: str,
) -> None:
    payload = ShopOrderEventPayload(
        shop_id=shop_id,
        shop_order_id=shop_order_id,
        public_code=public_code,
        status=status,
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

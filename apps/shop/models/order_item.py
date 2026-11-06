"""Таблица shop_order_items — строка заказа (снапшот позиции)."""

from __future__ import annotations

from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopOrderItem(PlatformModel):
    """Позиция в заказе. Таблица ``shop_order_items``.

    ``name_snapshot`` и ``price_minor`` фиксируются на момент заказа:
    правки каталога не дрейфуют уже оформленные заказы.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_order_items"
        indexes: list[Index] = [
            Index(["order_id"]),
        ]

    shop_order_item_id: str = DbField(db_pk=True, max_length=64)
    order_id: str = DbField(max_length=64)
    product_id: str = DbField(max_length=64)
    name_snapshot: str = DbField(max_length=300)
    price_minor: int = DbField(ge=0)
    qty: int = DbField(ge=1)
    discount_minor: int = DbField(default=0, ge=0)
    modifiers: list[dict[str, object]] = DbField(default_factory=list, db_type="JSONB")

    @classmethod
    async def list_by_order(cls, order_id: str) -> list[Self]:
        return await cls.objects.filter(order_id=order_id).all()

    @classmethod
    async def list_many_by_order_ids(cls, order_ids: list[str]) -> list[Self]:
        """Позиции пачки заказов — превью ленты кабинета без N+1."""
        if not order_ids:
            return []
        return await cls.objects.filter(order_id__in=order_ids).all()

    @classmethod
    async def create_many(cls, items: list[Self]) -> list[Self]:
        return await cls.objects.bulk_create(items)

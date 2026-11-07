"""Таблица shop_shelves — витринная полка ленты.

Полка — секция ленты витрины («Новинки», «Хиты», подборка владельца).
Одна сущность покрывает и ручные витрины (``manual`` + ``product_ids``),
и зеркала разделов (``category``), и вычисляемые секции
(``new``/``hits``/``comeback``/``usual``), и апсейл в корзине
(``upsell`` + ``placement='cart'``). Категории остаются таксономией
каталога — полка это витринная композиция, товар может входить в
несколько полок одновременно.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import (
    ShopShelfKind,
    ShopShelfLayout,
    ShopShelfPlacement,
)
from core.models.platform_model import PlatformModel


class ShopShelf(PlatformModel):
    """Витринная полка магазина. Таблица ``shop_shelves``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_shelves"
        indexes: list[Index] = [
            Index(["shop_id", "placement", "sort"]),
        ]

    shop_shelf_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    kind: ShopShelfKind = DbField(default=ShopShelfKind.MANUAL)
    layout: ShopShelfLayout = DbField(default=ShopShelfLayout.RAIL)
    placement: ShopShelfPlacement = DbField(default=ShopShelfPlacement.FEED)
    title: str = DbField(default="", max_length=120)
    subtitle: str = DbField(default="", max_length=200)
    product_ids: list[str] = DbField(default_factory=list, db_type="JSONB")
    category_id: str | None = DbField(default=None, max_length=64)
    limit: int = DbField(default=10, ge=1, le=50, db_column="item_limit")
    sort: int = DbField(default=0)
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_shelf_id: str) -> Self | None:
        return await cls.objects.filter(shop_shelf_id=shop_shelf_id).get_or_none()

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def list_active_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return (
            await cls.objects.filter(shop_id=shop_id, is_active=True)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def create(cls, shelf: Self) -> Self:
        return await cls.objects.create(instance=shelf)

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_id: str) -> int:
        row = await cls.objects.filter(shop_id=shop_id).order_by("-sort").first()
        return row.sort + 1 if row is not None else 0

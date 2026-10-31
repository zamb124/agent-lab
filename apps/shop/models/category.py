"""Таблица shop_categories — раздел каталога витрины."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopCategory(PlatformModel):
    """Категория товаров магазина. Таблица ``shop_categories``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_categories"
        indexes: list[Index] = [
            Index(["shop_id", "sort"]),
        ]

    shop_category_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    name: str = DbField(max_length=200)
    sort: int = DbField(default=0)
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_category_id: str) -> Self | None:
        return await cls.objects.filter(shop_category_id=shop_category_id).get_or_none()

    @classmethod
    async def list_by_shop(cls, shop_id: str) -> list[Self]:
        """Категории магазина по sort ASC. Предела нет."""
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def create(cls, category: Self) -> Self:
        return await cls.objects.create(instance=category)

    @classmethod
    async def next_sort(cls, shop_id: str) -> int:
        """Позиция для новой категории — за максимальной текущей."""
        row = (
            await cls.objects.filter(shop_id=shop_id)
            .order_by("-sort")
            .first()
        )
        return row.sort + 1 if row is not None else 0

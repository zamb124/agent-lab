"""Таблица shop_products — товар/блюдо витрины."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopProduct(PlatformModel):
    """Позиция каталога магазина. Таблица ``shop_products``.

    Поиск агрегатора идёт по ``name`` + ``description`` (pg_trgm GIN-индексы
    создаются миграцией). ``price_minor`` — минорные единицы ``Shop.currency``.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_products"
        indexes: list[Index] = [
            Index(["shop_id", "category_id", "sort"]),
            Index(["shop_id", "is_available"]),
        ]

    shop_product_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    category_id: str | None = DbField(default=None, max_length=64)
    name: str = DbField(max_length=300)
    description: str = DbField(default="", db_type="TEXT")
    price_minor: int = DbField(ge=0)
    photo_file_id: str | None = DbField(default=None, max_length=64)
    is_available: bool = DbField(default=True)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_product_id: str) -> Self | None:
        return await cls.objects.filter(shop_product_id=shop_product_id).get_or_none()

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        """Товары магазина по (category_id, sort). Предела нет."""
        return await cls.objects.filter(shop_id=shop_id).order_by("category_id", "sort").all()

    @classmethod
    async def list_available_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        """Доступные к заказу товары — вход снапшота витрины."""
        return (
            await cls.objects.filter(shop_id=shop_id, is_available=True)
            .order_by("category_id", "sort")
            .all()
        )

    @classmethod
    async def list_many_by_ids(cls, product_ids: list[str]) -> list[Self]:
        return await cls.objects.filter(shop_product_id__in=product_ids).all()

    @classmethod
    async def create(cls, product: Self) -> Self:
        return await cls.objects.create(instance=product)

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_id: str, category_id: str | None) -> int:
        row = (
            await cls.objects.filter(shop_id=shop_id, category_id=category_id)
            .order_by("-sort")
            .first()
        )
        return row.sort + 1 if row is not None else 0

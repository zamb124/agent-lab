"""Таблица shop_products — листинг товара на витрине (фасет).

``product_id`` — единый канонический идентификатор
``catalog_products.product_id`` (shared): имя, описание и галерея
живут в каталоге, витринные переопределения — в
``catalog_product_overrides`` scope ``shop:<shop_id>`` → ``shop``.
Здесь только витринная политика: цена, порция, метки, КБЖУ,
доступность, сортировка и раздел. Все публичные ссылки (заказы,
полки, избранное, модификаторы, подписки) держат ``product_id``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopProduct(PlatformModel):
    """Листинг товара витрины. Таблица ``shop_products``.

    ``price_minor`` — минорные единицы ``Shop.currency``. Поиск
    агрегатора идёт по проекции ``shop_market_items`` с эффективными
    (resolved) именами — прямые trgm-индексы тут не нужны.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_products"
        indexes: list[Index] = [
            Index(["shop_id", "product_id"], unique=True),
            Index(["shop_id", "category_id", "sort"]),
            Index(["shop_id", "is_available"]),
            Index(["product_id"]),
        ]

    shop_product_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    product_id: str = DbField(max_length=64)
    """``catalog_products.product_id`` — канонический id товара."""
    category_id: str | None = DbField(default=None, max_length=64)
    portion: str = DbField(default="", max_length=50)
    badges: list[str] = DbField(default_factory=list, db_type="JSONB")
    price_minor: int = DbField(ge=0)
    nutrition: dict[str, float] = DbField(default_factory=dict, db_type="JSONB")
    is_available: bool = DbField(default=True)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_product_id: str) -> Self | None:
        return await cls.objects.filter(shop_product_id=shop_product_id).get_or_none()

    @classmethod
    async def by_product_id(cls, product_id: str) -> Self | None:
        """Листинг по каноническому id товара (любой витрины)."""
        return await cls.objects.filter(product_id=product_id).get_or_none()

    @classmethod
    async def by_shop_and_product(
        cls, shop_id: str, product_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            shop_id=shop_id, product_id=product_id
        ).get_or_none()

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
    async def list_by_category_by_sort_asc(
        cls, shop_id: str, category_id: str | None
    ) -> list[Self]:
        """Товары одной категории по sort ASC."""
        return (
            await cls.objects.filter(shop_id=shop_id, category_id=category_id)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def list_by_shop_and_product_ids(
        cls, shop_id: str, product_ids: list[str]
    ) -> list[Self]:
        """Листинги магазина по каноническим id. Пустой вход — []."""
        if not product_ids:
            return []
        return await cls.objects.filter(
            shop_id=shop_id, product_id__in=product_ids
        ).all()

    @classmethod
    async def list_shop_ids_by_product_id(cls, product_id: str) -> list[str]:
        """Витрины, у которых есть листинг товара (фан-аут инвалидации)."""
        rows = await cls.objects.filter(product_id=product_id).all()
        return [row.shop_id for row in rows]

    @classmethod
    async def create(cls, product: Self) -> Self:
        return await cls.objects.create(instance=product)

    @classmethod
    async def count_by_shop(cls, shop_id: str) -> int:
        return await cls.objects.filter(shop_id=shop_id).count()

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_id: str, category_id: str | None) -> int:
        row = (
            await cls.objects.filter(shop_id=shop_id, category_id=category_id)
            .order_by("-sort")
            .first()
        )
        return row.sort + 1 if row is not None else 0

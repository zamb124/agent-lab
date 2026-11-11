"""Таблица shop_market_items — поисковая проекция листингов витрин.

Строки держат эффективный (resolved) контент: имя/описание/фото
после цепочки ``shop:<shop_id> → shop → base`` общего каталога.
Заполняется пересборкой в ``AggregateService.sync_shop_items`` —
из ребилда снапшота и consumer-группы ``shop`` на события
``catalog/product/*``. Прямой trgm-поиск по ``shop_products``
невозможен: контента там больше нет.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw

from core.models.platform_model import PlatformModel


class ShopMarketItem(PlatformModel):
    """Поисковая строка витрины. Таблица ``shop_market_items``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_market_items"
        indexes: list[Index] = [
            Index(["shop_id", "product_id"], unique=True),
            Index(["product_id"]),
        ]

    shop_market_item_id: str = DbField(db_pk=True, max_length=128)
    """Детерминированный PK ``{shop_id}:{product_id}`` — upsert без lookup."""
    shop_id: str = DbField(max_length=64)
    product_id: str = DbField(max_length=64)
    name: str = DbField(max_length=300)
    description: str = DbField(default="", max_length=1000)
    portion: str = DbField(default="", max_length=50)
    badges: list[str] = DbField(default_factory=list, db_type="JSONB")
    price_minor: int = DbField(ge=0)
    photo_file_id: str | None = DbField(default=None, max_length=64)
    updated_at: datetime = DbField()

    @classmethod
    async def replace_for_shop(
        cls, shop_id: str, items: list[Self]
    ) -> None:
        """Полная замена проекции витрины — атомарно в своей базе.

        Лок по ``shop_id`` сериализует пересборки (запрос и воркер
        пересобирают одну витрину конкурентно): без него delete+insert
        двух транзакций бьётся о PK ``{shop_id}:{product_id}``.
        """
        async with atomic(using="shop"):
            _ = await execute_raw(
                "SELECT pg_advisory_xact_lock(hashtext($1)::bigint) AS locked",
                [f"shop_market_items:{shop_id}"],
                using="shop",
            )
            await cls.delete_by_shop(shop_id)
            if items:
                _ = await cls.objects.bulk_create(items)

    @classmethod
    async def delete_by_shop(cls, shop_id: str) -> None:
        _ = await cls.objects.filter(shop_id=shop_id).delete()

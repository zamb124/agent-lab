"""Таблица shop_favorites — избранный товар покупателя на витрине.

Избранное — персональная витрина: живёт только в customer-сессии,
анонимный снапшот id'шники не несёт — ``/personal`` резолвит набор
для полки ``favorites`` и сердечек на карточках. Флаг темы
``features.favorites`` выключает фичу без следа в UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopFavorite(PlatformModel):
    """Позиция избранного. Таблица ``shop_favorites``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_favorites"
        indexes: list[Index] = [
            Index(["shop_id", "customer_id"]),
            Index(["customer_id"]),
        ]
        unique_together: list[tuple[str, str]] = [
            ("product_id", "customer_id"),
        ]

    shop_favorite_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    product_id: str = DbField(max_length=64)
    customer_id: str = DbField(max_length=64)
    created_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, favorite_id: str) -> Self | None:
        return await cls.objects.filter(shop_favorite_id=favorite_id).get_or_none()

    @classmethod
    async def find_by_product_and_customer(
        cls, product_id: str, customer_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            product_id=product_id, customer_id=customer_id
        ).get_or_none()

    @classmethod
    async def list_by_shop_customer_by_created_desc(
        cls, shop_id: str, customer_id: str
    ) -> list[Self]:
        return (
            await cls.objects.filter(shop_id=shop_id, customer_id=customer_id)
            .order_by("-created_at")
            .all()
        )

    @classmethod
    async def create(cls, favorite: Self) -> Self:
        return await cls.objects.create(instance=favorite)

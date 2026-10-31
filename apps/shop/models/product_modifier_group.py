"""Связь товара с группой модификаторов и контекстные overrides.

``min_selected``/``max_selected`` переопределяют лимиты группы для
конкретного товара (Uber: большой боул — 4 топпинга, обычный — 3).
"""

from __future__ import annotations

from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopProductModifierGroup(PlatformModel):
    """M2M-связь продукт ↔ группа. Таблица ``shop_product_modifier_groups``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_product_modifier_groups"
        indexes: list[Index] = [
            Index(["product_id", "sort"]),
            Index(["group_id"]),
        ]

    product_id: str = DbField(db_pk=True, max_length=64)
    group_id: str = DbField(db_pk=True, max_length=64)
    sort: int = DbField(default=0)
    min_selected: int | None = DbField(default=None, ge=0)
    max_selected: int | None = DbField(default=None, ge=1)

    @classmethod
    async def list_by_product_by_sort_asc(cls, product_id: str) -> list[Self]:
        return await cls.objects.filter(product_id=product_id).order_by("sort").all()

    @classmethod
    async def list_by_products(cls, product_ids: list[str]) -> list[Self]:
        if not product_ids:
            return []
        return await cls.objects.filter(product_id__in=product_ids).all()

    @classmethod
    async def list_by_groups(cls, group_ids: list[str]) -> list[Self]:
        if not group_ids:
            return []
        return await cls.objects.filter(group_id__in=group_ids).all()

    @classmethod
    async def get_link(cls, product_id: str, group_id: str) -> Self | None:
        return await cls.objects.filter(product_id=product_id, group_id=group_id).get_or_none()

    @classmethod
    async def create(cls, link: Self) -> Self:
        return await cls.objects.create(instance=link)

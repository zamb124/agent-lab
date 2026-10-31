"""Переиспользуемая группа модификаторов магазина.

Универсальная модель (Uber Eats / Toast / iiko): размер, добавка,
«убрать ингредиент» — всё группа + опции. ``price_mode``:
``delta`` — опция прибавляет к базе, ``absolute`` — цена опции
замещает базовую цену товара (варианты/размеры).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import (
    ModifierGroupKind,
    ModifierPriceMode,
    ModifierSelectionMode,
)
from core.models.platform_model import PlatformModel


class ShopModifierGroup(PlatformModel):
    """Группа модификаторов. Таблица ``shop_modifier_groups``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_modifier_groups"
        indexes: list[Index] = [
            Index(["shop_id", "sort"]),
        ]

    shop_modifier_group_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    name: str = DbField(max_length=200)
    description: str = DbField(default="", max_length=500)
    kind: ModifierGroupKind = DbField(default=ModifierGroupKind.ADDON)
    selection_mode: ModifierSelectionMode = DbField(default=ModifierSelectionMode.MULTI)
    min_selected: int = DbField(default=0, ge=0)
    max_selected: int | None = DbField(default=None, ge=1)
    price_mode: ModifierPriceMode = DbField(default=ModifierPriceMode.DELTA)
    is_active: bool = DbField(default=True)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, group_id: str) -> Self | None:
        return await cls.objects.filter(shop_modifier_group_id=group_id).get_or_none()

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def create(cls, group: Self) -> Self:
        return await cls.objects.create(instance=group)

"""Опция внутри группы модификаторов: цена, дефолт, лимиты, nested."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopModifierOption(PlatformModel):
    """Опция модификатора. Таблица ``shop_modifier_options``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_modifier_options"
        indexes: list[Index] = [
            Index(["group_id", "sort"]),
        ]

    shop_modifier_option_id: str = DbField(db_pk=True, max_length=64)
    group_id: str = DbField(max_length=64)
    name: str = DbField(max_length=200)
    price_minor: int = DbField(default=0, ge=0)
    photo_file_id: str | None = DbField(default=None, max_length=64)
    nutrition_delta: dict[str, float] = DbField(default_factory=dict, db_type="JSONB")
    is_default: bool = DbField(default=False)
    is_available: bool = DbField(default=True)
    max_per_option: int = DbField(default=1, ge=1)
    nested_group_id: str | None = DbField(default=None, max_length=64)
    external_id: str | None = DbField(default=None, max_length=128)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, option_id: str) -> Self | None:
        return await cls.objects.filter(shop_modifier_option_id=option_id).get_or_none()

    @classmethod
    async def list_by_group_by_sort_asc(cls, group_id: str) -> list[Self]:
        return await cls.objects.filter(group_id=group_id).order_by("sort").all()

    @classmethod
    async def list_many_by_ids(cls, option_ids: list[str]) -> list[Self]:
        if not option_ids:
            return []
        return await cls.objects.filter(shop_modifier_option_id__in=option_ids).all()

    @classmethod
    async def create(cls, option: Self) -> Self:
        return await cls.objects.create(instance=option)

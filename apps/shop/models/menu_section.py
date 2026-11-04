"""Таблица shop_menu_sections — раздел конкретного меню."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopMenuSection(PlatformModel):
    """Раздел меню. Таблица ``shop_menu_sections``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_menu_sections"
        indexes: list[Index] = [
            Index(["shop_menu_id", "parent_id", "sort"]),
        ]

    shop_menu_section_id: str = DbField(db_pk=True, max_length=64)
    shop_menu_id: str = DbField(max_length=64)
    parent_id: str | None = DbField(default=None, max_length=64)
    name: str = DbField(max_length=200)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_menu_section_id: str) -> Self | None:
        return await cls.objects.filter(
            shop_menu_section_id=shop_menu_section_id
        ).get_or_none()

    @classmethod
    async def list_by_menu_by_sort_asc(cls, shop_menu_id: str) -> list[Self]:
        return (
            await cls.objects.filter(shop_menu_id=shop_menu_id).order_by("sort").all()
        )

    @classmethod
    async def list_children_by_parent_by_sort_asc(
        cls, shop_menu_id: str, parent_id: str | None
    ) -> list[Self]:
        return (
            await cls.objects.filter(shop_menu_id=shop_menu_id, parent_id=parent_id)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def find_by_menu_and_name(
        cls, shop_menu_id: str, name: str
    ) -> Self | None:
        return await cls.objects.filter(
            shop_menu_id=shop_menu_id, name=name
        ).get_or_none()

    @classmethod
    async def create(cls, section: Self) -> Self:
        return await cls.objects.create(instance=section)

    @classmethod
    async def next_sort_by_sort_desc(
        cls, shop_menu_id: str, parent_id: str | None
    ) -> int:
        row = (
            await cls.objects.filter(shop_menu_id=shop_menu_id, parent_id=parent_id)
            .order_by("-sort")
            .first()
        )
        return row.sort + 1 if row is not None else 0

    @classmethod
    async def delete_by_menu(cls, shop_menu_id: str) -> int:
        return await cls.objects.filter(shop_menu_id=shop_menu_id).delete()

"""Таблица shop_menus — меню заведения."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import ShopMenuStatus
from core.models.platform_model import PlatformModel


class ShopMenu(PlatformModel):
    """Меню заведения. Таблица ``shop_menus``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_menus"
        indexes: list[Index] = [
            Index(["shop_id", "status", "sort"]),
        ]

    shop_menu_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    name: str = DbField(max_length=200)
    status: ShopMenuStatus = DbField(default=ShopMenuStatus.DRAFT)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_menu_id: str) -> Self | None:
        return await cls.objects.filter(shop_menu_id=shop_menu_id).get_or_none()

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def list_active_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return (
            await cls.objects.filter(shop_id=shop_id, status=ShopMenuStatus.ACTIVE)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def create(cls, menu: Self) -> Self:
        return await cls.objects.create(instance=menu)

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_id: str) -> int:
        row = await cls.objects.filter(shop_id=shop_id).order_by("-sort").first()
        return row.sort + 1 if row is not None else 0

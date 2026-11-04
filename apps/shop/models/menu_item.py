"""Таблица shop_menu_items — позиция меню со ссылкой на блюдо каталога."""

from __future__ import annotations

from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopMenuItem(PlatformModel):
    """Позиция меню. Таблица ``shop_menu_items``.

    Цена витрины: ``price_minor_override`` если задан, иначе ``ShopProduct.price_minor``.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_menu_items"
        indexes: list[Index] = [
            Index(["shop_menu_id", "shop_menu_section_id", "sort"]),
            Index(["shop_product_id"]),
        ]
        unique_together: list[tuple[str, str]] = [
            ("shop_menu_id", "shop_product_id"),
        ]

    shop_menu_item_id: str = DbField(db_pk=True, max_length=64)
    shop_menu_id: str = DbField(max_length=64)
    shop_menu_section_id: str = DbField(max_length=64)
    shop_product_id: str = DbField(max_length=64)
    price_minor_override: int | None = DbField(default=None, ge=0)
    is_available: bool = DbField(default=True)
    sort: int = DbField(default=0)

    @classmethod
    async def get_by_id(cls, shop_menu_item_id: str) -> Self | None:
        return await cls.objects.filter(
            shop_menu_item_id=shop_menu_item_id
        ).get_or_none()

    @classmethod
    async def list_by_menu_by_sort_asc(cls, shop_menu_id: str) -> list[Self]:
        return (
            await cls.objects.filter(shop_menu_id=shop_menu_id)
            .order_by("shop_menu_section_id", "sort")
            .all()
        )

    @classmethod
    async def list_by_section_by_sort_asc(
        cls, shop_menu_section_id: str
    ) -> list[Self]:
        return (
            await cls.objects.filter(shop_menu_section_id=shop_menu_section_id)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def list_by_product(cls, shop_product_id: str) -> list[Self]:
        return await cls.objects.filter(shop_product_id=shop_product_id).all()

    @classmethod
    async def find_by_menu_and_product(
        cls, shop_menu_id: str, shop_product_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            shop_menu_id=shop_menu_id, shop_product_id=shop_product_id
        ).get_or_none()

    @classmethod
    async def exists_for_product(cls, shop_product_id: str) -> bool:
        row = await cls.objects.filter(shop_product_id=shop_product_id).first()
        return row is not None

    @classmethod
    async def count_for_menu(cls, shop_menu_id: str) -> int:
        return await cls.objects.filter(shop_menu_id=shop_menu_id).count()

    @classmethod
    async def create(cls, item: Self) -> Self:
        return await cls.objects.create(instance=item)

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_menu_section_id: str) -> int:
        row = (
            await cls.objects.filter(shop_menu_section_id=shop_menu_section_id)
            .order_by("-sort")
            .first()
        )
        return row.sort + 1 if row is not None else 0

    @classmethod
    async def delete_by_menu(cls, shop_menu_id: str) -> int:
        return await cls.objects.filter(shop_menu_id=shop_menu_id).delete()

    def effective_price_minor(self, catalog_price_minor: int) -> int:
        if self.price_minor_override is not None:
            return self.price_minor_override
        return catalog_price_minor

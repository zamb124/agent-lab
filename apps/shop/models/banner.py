"""Таблица shop_banners — сторис-карточка верха ленты витрины.

Баннер — визуальная промо-карточка с собственной картинкой
(загруженной или сгенерированной AI) и deeplink'ом внутрь витрины
(``product:<id>``, ``category:<id>``, ``shelf:<id>``) или наружу
(``url:<https…>``). ``window`` — необязательный период показа
(сезонные кампании): пустой — показывается всегда.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class ShopBanner(PlatformModel):
    """Промо-баннер витрины. Таблица ``shop_banners``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_banners"
        indexes: list[Index] = [
            Index(["shop_id", "sort"]),
        ]

    shop_banner_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    title: str = DbField(default="", max_length=120)
    subtitle: str = DbField(default="", max_length=200)
    image_file_id: str | None = DbField(default=None, max_length=64)
    link: str = DbField(default="", max_length=300)
    window: JsonObject = DbField(default_factory=dict, db_type="JSONB", db_column="display_window")
    sort: int = DbField(default=0)
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_banner_id: str) -> Self | None:
        return await cls.objects.filter(shop_banner_id=shop_banner_id).get_or_none()

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def list_active_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return (
            await cls.objects.filter(shop_id=shop_id, is_active=True)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def create(cls, banner: Self) -> Self:
        return await cls.objects.create(instance=banner)

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_id: str) -> int:
        row = await cls.objects.filter(shop_id=shop_id).order_by("-sort").first()
        return row.sort + 1 if row is not None else 0

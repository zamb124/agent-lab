"""Акции магазина — полиморфный condition + action реестр.

Модель мировых практик (Deliveroo/Zopping/Toast): промо = ``condition``
(когда срабатывает) + ``action`` (что делает) + ``window`` (временные
окна — счастливые часы в таймзоне магазина) + ``priority``/``stacking``
(детерминизм применения). Новые механики добавляются типами в JSONB,
без миграций схемы.

Condition types: ``always``, ``min_qty``, ``min_total``, ``section_qty``,
``items_present``.
Action types: ``percent_items``, ``amount_order``, ``percent_order``,
``fixed_bundle_price``, ``n_plus_m_free``, ``free_delivery``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import PromoStacking
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class ShopPromo(PlatformModel):
    """Акция магазина. Таблица ``shop_promos``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_promos"
        indexes: list[Index] = [
            Index(["shop_id", "is_active", "sort"]),
        ]

    shop_promo_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    name: str = DbField(max_length=200)
    is_active: bool = DbField(default=True)
    sort: int = DbField(default=0)
    priority: int = DbField(default=0)
    stacking: PromoStacking = DbField(default=PromoStacking.ALL)
    window: JsonObject = DbField(default_factory=dict, db_type="JSONB", db_column="active_window")
    condition: JsonObject = DbField(db_type="JSONB")
    action: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, promo_id: str) -> Self | None:
        return await cls.objects.filter(shop_promo_id=promo_id).get_or_none()

    @classmethod
    async def list_active_by_shop_by_priority_desc(cls, shop_id: str) -> list[Self]:
        return (
            await cls.objects.filter(shop_id=shop_id, is_active=True)
            .order_by("-priority")
            .order_by("sort")
            .all()
        )

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def create(cls, promo: Self) -> Self:
        return await cls.objects.create(instance=promo)

    @classmethod
    async def next_sort(cls, shop_id: str) -> int:
        promos = await cls.objects.filter(shop_id=shop_id).all()
        return max((p.sort for p in promos), default=-1) + 1

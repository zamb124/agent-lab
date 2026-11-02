"""Таблица shop_tables — стол зала для заказа «в заведении».

Стол получает свой QR: ``?table=<shop_table_id>`` на витрине предвыбирает
тип выдачи ``onsite`` и подставляет метку стола в заказ.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopTable(PlatformModel):
    """Стол/место зала магазина. Таблица ``shop_tables``.

    ``label`` — как гость и кухня называют место («Стол 5», «У окна»);
    в заказ кладётся снапшот label — переименование стола не переписывает
    историю заказов.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_tables"
        indexes: list[Index] = [
            Index(["shop_id"]),
        ]

    shop_table_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    label: str = DbField(max_length=64)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_table_id: str) -> Self | None:
        return await cls.objects.filter(shop_table_id=shop_table_id).get_or_none()

    @classmethod
    async def list_by_shop_by_created_asc(cls, shop_id: str) -> list[Self]:
        """Столы магазина по created_at ASC — порядок заведения столиков."""
        return await cls.objects.filter(shop_id=shop_id).order_by("created_at").all()

    @classmethod
    async def create(cls, table: Self) -> Self:
        return await cls.objects.create(instance=table)

"""Таблица склада."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import MONEY_DB, QTY_DB, STOCK_DB
from core.models.platform_model import PlatformModel


class StockValueLayerConsumption(PlatformModel):
    """Развязка FIFO-потребления: какой in-layer закрыл out-layer.

    Таблица ``stock_value_layer_consumptions``.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_value_layer_consumptions"
        indexes: list[Index] = [
            Index(["company_id", "out_layer_id"]),
            Index(["company_id", "in_layer_id"]),
        ]

    consumption_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    out_layer_id: str = DbField(max_length=64)
    in_layer_id: str = DbField(max_length=64)
    quantity: Decimal = DbField(db_type=QTY_DB)
    value: Decimal = DbField(db_type=MONEY_DB)
    created_at: datetime = DbField()

    @classmethod
    async def write(cls, consumption: Self) -> Self:
        return await cls.objects.create(instance=consumption)

    @classmethod
    async def list_for_out_layer(
        cls, company_id: str, out_layer_id: str
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, out_layer_id=out_layer_id
        ).all()

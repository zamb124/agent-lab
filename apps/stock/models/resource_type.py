"""Типы складских ресурсов (stock_resource_types) — «классы техники».

По аналогии с SAP EWM resource type: описывает класс ресурса
(рохля, штабелёр, ричтрак, пеший отборщик) и его возможности — что он
может возить и куда ему можно ехать. Это справочник возможностей,
на основании которого система назначает задания: «этот тяжёлый паллет
отдадим штабелёру, а не пешему отборщику».
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import MONEY_DB, STOCK_DB
from core.models.platform_model import PlatformModel


class StockResourceType(PlatformModel):
    """Возможности класса ресурса. Таблица ``stock_resource_types``.

    * ``allowed_container_type_ids`` — какую тару возит (пусто — любую);
      «рохля берёт паллету, короб — нет».
    * ``handles_loose`` — работает ли с россыпью без тары
      (пеший отборщик — да; штабелёр под паллеты — нет).
    * ``max_level`` — максимальный ярус, до которого достаёт
      (пеший — 1, ричтрак — любой).
    * ``max_load_weight`` — грузоподъёмность за рейс.
    * ``storage_type_ids`` — в какие зоны (типы хранения) допускается;
      пусто — весь склад. «Морозильник» можно закрыть для обычных
      погрузчиков.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_resource_types"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "name"], unique=True),
        ]

    resource_type_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    name: str = DbField(max_length=128)
    allowed_container_type_ids: list[str] = DbField(default_factory=list)
    """Пусто — ресурс работает с любыми контейнерами."""
    handles_loose: bool = DbField(default=True)
    """Работает с россыпью (без контейнера)."""
    max_level: int | None = DbField(default=None)
    """Максимальный ярус, до которого ресурс достаёт (None — без лимита)."""
    max_load_weight: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    storage_type_ids: list[str] = DbField(default_factory=list)
    """Доступные типы хранения (зоны); пусто — весь склад."""
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, resource_type_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, resource_type_id=resource_type_id
        ).get_or_none()

    @classmethod
    async def list_for_warehouse(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("name").all()

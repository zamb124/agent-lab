"""Типы хранения ячеек (stock_storage_types) — «правила полки».

По аналогии с SAP EWM storage type: это не сама ячейка, а её
«характер» — набор правил, которые решают, что можно положить и как
отбирать. Ячейке задают тип хранения; при каждой попытке положить
проверяются ограничения (storage_rules.check_placement в момент
проведения движения и PlacementService.suggest при подсказке).

Примеры типов хранения:
  * «Паллетная зона» — только контейнеры, не больше 1 паллеты на ячейку;
  * «Полка подбора» — только россыпь, смешивание товаров запрещено;
  * «Карантин» — заблокированная зона брака и возвратов;
  * «Оверсайз» — без ограничений по весу, FIFO-отбор.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import MONEY_DB, STOCK_DB
from apps.stock.models.enums import (
    StockContainerPolicy,
    StockProductMixing,
    StockPutawayStrategy,
    StockRemovalStrategy,
)
from core.models.platform_model import PlatformModel


class StockStorageType(PlatformModel):
    """Характер ячейки: правила размещения и отбора. Таблица ``stock_storage_types``.

    Поля — правила для кладовщика/системы:

    * ``container_policy`` — ``any``/``loose_only``/``container_only»:
      «сюда только паллеты» или «сюда только штуки, без тары».
    * ``allowed_container_type_ids`` — какие типы тары допустимы
      (пусто — любые). «Паллетная зона» откажет коробу.
    * ``max_containers`` — сколько тары влезает (1 = «одна паллета на
      место»).
    * ``product_mixing`` — ``mixed``/``same_product``/``empty_only»:
      можно ли смешивать разные товары в одной ячейке; ``empty_only``
      = «ячейка всегда под один груз, пока не опустеет».
    * ``allow_mixed_lots`` — можно ли смешивать разные партии одного
      товара (учёт сроков годности vs компактность).
    * ``max_weight``/``max_volume`` — ёмкость по массе/объёму полки.
    * ``putaway_strategies`` — цепочка стратегий поиска ячейки для
      прихода (например «сначала пустую ячейку, потом к тому же товару»).
    * ``removal_strategy`` — порядок отбора (``fifo``/``fefo``/``lifo»):
      правило «откуда отгружать» (FEFO — первым уходит то, что раньше
      испортится); ``None`` — наследуется стратегия склада.
    * ``cycle_count_days`` — период циклического пересчёта ячеек этого
      типа (Фаза 6).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_storage_types"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "name"], unique=True),
        ]

    storage_type_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    name: str = DbField(max_length=128)
    container_policy: StockContainerPolicy = DbField(
        default=StockContainerPolicy.ANY
    )
    allowed_container_type_ids: list[str] = DbField(default_factory=list)
    """Пусто — любые типы контейнеров допустимы."""
    max_containers: int | None = DbField(default=None)
    """Максимум контейнеров в ячейке (1 — одна паллета на место)."""
    product_mixing: StockProductMixing = DbField(default=StockProductMixing.MIXED)
    allow_mixed_lots: bool = DbField(default=True)
    max_weight: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    max_volume: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    putaway_strategies: list[StockPutawayStrategy] = DbField()
    """Цепочка `StockPutawayStrategy` — порядок поиска ячейки приёмки."""
    removal_strategy: StockRemovalStrategy | None = DbField(default=None)
    """Переопределение стратегии склада; ``None`` — правила склада."""
    cycle_count_days: int | None = DbField(default=None)
    """Период циклического пересчёта ячеек этого типа (Фаза 6)."""
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, storage_type_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, storage_type_id=storage_type_id
        ).get_or_none()

    @classmethod
    async def found_in_company_by_ids(
        cls, company_id: str, storage_type_ids: list[str]
    ) -> dict[str, Self]:
        if not storage_type_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, storage_type_id__in=storage_type_ids
        ).all()
        return {row.storage_type_id: row for row in rows}

    @classmethod
    async def list_for_warehouse_by_name_asc(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Все типы хранения склада, ORDER BY name ASC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("name").all()

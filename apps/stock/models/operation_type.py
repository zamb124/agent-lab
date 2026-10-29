"""Типы складских операций (stock_operation_types) — «виды накладных».

«Тип операции» — бланк документа: «приёмка», «отгрузка», «внутреннее
перемещение», «возврат поставщику», «инвентаризация». Он задаёт, какие
локации используются по умолчанию (источник/назначение), какой
префикс номеров накладных, разрешены ли новые партии и какая политика
резерва/доказки.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import STOCK_DB
from apps.stock.models.enums import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockOperationCode,
)
from core.models.platform_model import PlatformModel


class StockOperationType(PlatformModel):
    """«Вид накладной» — шаблон бизнес-операции склада. Таблица ``stock_operation_types``.

    Что задаёт тип операции:

    * ``code`` — класс операции (``receipt``/``delivery``/``internal``/
      ``adjustment``/``return``) — главный бизнес-смысл;
    * ``prefix`` — префикс номеров накладных этого типа (``WH/IN``,
      ``WH/OUT``, ``ADJ``);
    * ``source_location_id``/``destination_location_id`` — локации
      по умолчанию для строк;
    * ``reservation_policy`` — как резервировать: ``manual``
      (явной командой assign) или ``at_confirm`` (сразу при
      подтверждении накладной);
    * ``backorder_policy`` — что делать с нехваткой: ``always``
      (создать доказку), ``never`` (ошибка), ``ask`` (спросить);
    * ``create_lots``/``use_existing_lots`` — разрешены ли новые/
      обязательны существующие партии;
    * ``return_operation_type_id`` — какой тип использовать для
      оформления возврата от этого типа.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_operation_types"
        indexes: list[Index] = [
            Index(["company_id", "code", "warehouse_id"], unique=True),
            Index(["company_id", "warehouse_id"]),
        ]

    operation_type_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    code: StockOperationCode = DbField()
    name: str = DbField(max_length=255)
    default_source_location_id: str | None = DbField(default=None, max_length=64)
    default_dest_location_id: str | None = DbField(default=None, max_length=64)
    reservation_policy: ReservationPolicy = DbField(default=ReservationPolicy.MANUAL)
    backorder_policy: BackorderPolicy = DbField(default=BackorderPolicy.ALWAYS)
    putaway_mode: ReflexMode = DbField(default=ReflexMode.RULE)
    putaway_flow_id: str | None = DbField(default=None, max_length=64)
    auto_validate: bool = DbField(default=False)
    name_prefix: str | None = DbField(default=None, max_length=32)
    """Префикс номеров transfer'ов этого типа (`WH/IN` по умолчанию)."""
    create_lots: bool = DbField(default=True)
    """Партии/серийники можно заводить на приёмке этой операции."""
    use_existing_lots: bool = DbField(default=True)
    """Партии должны существовать заранее (False — только из create_lots)."""
    return_operation_type_id: str | None = DbField(default=None, max_length=64)
    """Тип операции для возвратов; пусто — обратный тому же типу."""
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, operation_type_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, operation_type_id=operation_type_id
        ).get_or_none()

    @classmethod
    async def list_for_warehouse_by_code_asc(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Все типы операций склада, ORDER BY code ASC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("code").all()

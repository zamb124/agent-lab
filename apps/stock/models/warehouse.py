"""Площадки склада компании (stock_warehouses).

«Склад» — верхний уровень адресации: у него есть здание/территория,
своя полоса сериализации (все складские мутации этого склада идут по
одной линии), тип операций и дерево локаций. Один компания может иметь
несколько складов («основной», «розничный», «РЦ»).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from apps.stock.models.common import STOCK_DB
from apps.stock.models.enums import StockRemovalStrategy
from core.models.platform_model import PlatformModel
from core.types import require_json_object


class StockWarehouse(PlatformModel):
    """Площадка склада компании. Таблица ``stock_warehouses``.

    Ключевые бизнес-поля:

    * ``code`` — короткий префикс склада в номерах накладных
      (``WH/IN``, ``WH/OUT``);
    * ``removal_strategy`` — стратегия отбора по умолчанию
      (FIFO/LIFO/FEFO): последнее звено цепочки «товар → тип хранения
      ячейки → склад», поэтому всегда задана.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_warehouses"
        indexes: list[Index] = [Index(["company_id", "code"], unique=True)]

    warehouse_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    code: str = DbField(max_length=32)
    name: str = DbField(max_length=255)
    view_location_id: str = DbField(max_length=64)
    stock_location_id: str = DbField(max_length=64)
    removal_strategy: StockRemovalStrategy = DbField()
    """Стратегия отбора по умолчанию — обязательна — без неё цепочка не замыкается."""
    created_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, warehouse_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).get_or_none()

    @classmethod
    async def list_for_company(
        cls, company_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).order_by("code").limit(
            limit
        ).offset(offset).all()

    @classmethod
    async def count_for_company(cls, company_id: str) -> int:
        return await cls.objects.filter(company_id=company_id).count()

    @classmethod
    async def list_company_ids(cls) -> list[str]:
        """Все компании, у которых есть склады — итератор фоновых тиков."""
        rows = await execute_raw(
            "SELECT DISTINCT company_id FROM stock_warehouses ORDER BY company_id",
            [],
            using=STOCK_DB,
        )
        ids: list[str] = []
        for row in rows:
            parsed = require_json_object(row, "company_id")
            cid = parsed.get("company_id")
            if isinstance(cid, str) and cid:
                ids.append(cid)
        return ids

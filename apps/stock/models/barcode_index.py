"""Индекс штрихкодов (stock_barcodes) — «телефонная книга складских меток».

Прямая связка «штрихкод → сущность»: отсканировал метку — сразу знаешь,
что это (товар, локация, контейнер, партия, накладная, упаковка,
ресурс). Это ЕДИНСТВЕННАЯ точка хранения сканируемых кодов — доменные
сущности своих barcode-полей не имеют, поэтому индекс не может
рассинхронизироваться с колонкой-«вторым источником». Одна сущность
может держать несколько кодов (альтернативные этикетки товара), один
код — только одну сущность.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import UniqueViolationError

from apps.stock.models.common import STOCK_DB, new_id
from apps.stock.models.enums import (
    StockBarcodeEntityType,
)
from core.errors.boundary import PlatformConflictError
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockBarcodeIndex(PlatformModel):
    """Штрихкод → сущность. Таблица ``stock_barcodes``.

    `(company_id, barcode)` unique — единая атомарная точка уникальности
    «один код — один носитель» (product/location/package/lot/transfer).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_barcodes"
        indexes: list[Index] = [
            Index(["company_id", "barcode"], unique=True),
            Index(["company_id", "entity_type", "entity_id"]),
        ]

    barcode_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    barcode: str = DbField(max_length=128)
    entity_type: StockBarcodeEntityType = DbField()
    entity_id: str = DbField(max_length=64)
    created_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def bind(
        cls,
        *,
        company_id: str,
        barcode: str,
        entity_type: StockBarcodeEntityType,
        entity_id: str,
    ) -> Self:
        """Привязать код к сущности — единственная точка записи индекса.

        ``unique (company_id, barcode)`` — один код = один носитель:
        один и тот же штрихкод не может быть и товаром, и ячейкой.
        Повторная привязка того же кода к той же сущности — no-op;
        к другой — ``barcode_conflict``. Вызов внутри lane-тела
        делает привязку атомарной с доменной записью (накладная и её
        код появляются одним коммитом).
        """
        code = barcode.strip()
        if not code:
            raise PlatformConflictError(
                "Barcode must be non-empty", error_code="barcode_empty"
            )
        existing = await cls.resolve(company_id, code)
        if existing is not None:
            if existing.entity_id == entity_id and existing.entity_type == entity_type:
                return existing
            raise PlatformConflictError(
                "Barcode is already bound to another entity",
                error_code="barcode_conflict",
            )
        try:
            return await cls.create(
                cls(
                    barcode_id=new_id("bcd"),
                    company_id=company_id,
                    barcode=code,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    created_at=utcnow(),
                )
            )
        except UniqueViolationError as exc:
            raise PlatformConflictError(
                "Barcode is already bound to another entity",
                error_code="barcode_conflict",
            ) from exc

    @classmethod
    async def resolve(
        cls, company_id: str, barcode: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, barcode=barcode
        ).get_or_none()

    @classmethod
    async def release_entity(cls, company_id: str, entity_id: str) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, entity_id=entity_id
        ).delete()

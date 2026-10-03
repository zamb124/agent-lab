"""Единицы измерения и товарные упаковки (stock_uom).

Одна таблица — два рода строк (SAP-стиль «alternative unit of
measure»):

* ``product_id IS NULL`` — глобальная ЕИ компании («штука», «кг»):
  ``category`` + ``factor`` к референсу категории задают конвертацию
  (1 кг = 1000 г при референсе «г»). Уникальность — ``(company_id,
  name)``.
* ``product_id IS NOT NULL`` — упаковка конкретного товара («короб
  24 шт»): ``factor`` = сколько референс-единиц категории в одной
  упаковке (для штучного товара — просто количество: короб 24 шт →
  factor=24). Упаковка живёт в категории базовой ЕИ товара, поэтому
  ``convert`` переводит «3 коробки» в базовые единицы без особого
  кода. Уникальность — ``(company_id, product_id, name)``: у муки и у
  печенья могут быть свои «короб 24 шт» с разным весом.

Упаковка дополнительно несёт ``container_type_id`` (в какой таре её
принято хранить — приёмка «по упаковке» создаст контейнер-паллету) и
``weight``/``volume`` (масса/объём одной упаковки для грузоподъёмности
и габаритов). Штрихкод упаковки (GTIN-14) привязан в
``stock_barcodes`` под ``entity_type=packaging`` и указывает прямо на
строку ``stock_uom``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import QTY_DB, STOCK_DB, STOCK_ZERO
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.models.platform_model import PlatformModel


class UnitOfMeasure(PlatformModel):
    """Единица измерения или товарная упаковка. Таблица ``stock_uom``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_uom"
        indexes: list[Index] = [
            Index(
                ["company_id", "name"],
                unique=True,
                where="product_id IS NULL",
            ),
            Index(
                ["company_id", "product_id", "name"],
                unique=True,
                where="product_id IS NOT NULL",
            ),
        ]

    uom_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    name: str = DbField(max_length=128)
    category: str = DbField(max_length=64)
    factor: Decimal = DbField(db_type=QTY_DB)
    is_reference: bool = DbField(default=False)
    product_id: str | None = DbField(default=None, max_length=64)
    container_type_id: str | None = DbField(default=None, max_length=64)
    weight: Decimal | None = DbField(default=None, db_type=QTY_DB)
    volume: Decimal | None = DbField(default=None, db_type=QTY_DB)

    @classmethod
    async def by_id(cls, company_id: str, uom_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, uom_id=uom_id
        ).get_or_none()

    @classmethod
    async def list_for_company(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).order_by(
            "category", "name"
        ).all()

    @classmethod
    async def list_global(cls, company_id: str) -> list[Self]:
        """Только глобальные ЕИ (``product_id IS NULL``) — справочник
        конвертации, не упаковки."""
        return await cls.objects.filter(
            company_id=company_id, product_id__isnull=True
        ).order_by("category", "name").all()

    @classmethod
    async def list_packagings(
        cls, company_id: str, product_id: str | None = None
    ) -> list[Self]:
        """Товарные упаковки (``product_id IS NOT NULL``), опционально —
        одного товара."""
        query = cls.objects.filter(
            company_id=company_id, product_id__isnull=False
        )
        if product_id is not None:
            query = query.filter(product_id=product_id)
        return await query.order_by("product_id", "factor").all()

    @classmethod
    async def exists_by_name(cls, company_id: str, name: str) -> bool:
        return await cls.objects.filter(company_id=company_id, name=name).exists()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def delete_uom(cls, company_id: str, uom_id: str) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, uom_id=uom_id
        ).delete()

    @classmethod
    async def convert(
        cls,
        quantity: Decimal,
        from_uom_id: str,
        to_uom_id: str,
    ) -> Decimal:
        """Перевод количества между ЕИ одной категории через reference-фактор."""
        if from_uom_id == to_uom_id:
            return quantity
        pair = await cls.get_many([from_uom_id, to_uom_id])
        src = pair.get(from_uom_id)
        dst = pair.get(to_uom_id)
        if src is None or dst is None:
            raise PlatformNotFoundError(
                "Unit of measure not found", error_code="uom_not_found"
            )
        if src.category != dst.category:
            raise PlatformConflictError(
                "UoM category mismatch",
                error_code="uom_category_mismatch",
            )
        if src.factor == STOCK_ZERO or dst.factor == STOCK_ZERO:
            raise PlatformConflictError(
                "UoM factor is zero", error_code="uom_factor_zero"
            )
        return quantity * src.factor / dst.factor

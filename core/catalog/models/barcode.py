"""Торговые штрихкоды (catalog_barcodes) — GTIN/EAN и коды упаковок.

Прямая связка «штрихкод → товар или упаковка каталога»:
``uom_id IS NULL`` — код самого товара (EAN-13/внутренний артикульный
код), ``uom_id`` — код упаковки (GTIN-14 короба) и указывает на строку
``catalog_uoms``. ``unique (company_id, barcode)`` — один код = один
носитель.

Логистические метки склада (ячейки, контейнеры, партии, накладные,
ресурсы, SSCC) живут в ``stock_barcodes`` — они биндятся внутри
lane-транзакций склада и не могут уехать в shared. Resolve на стороне
склада смотрит сначала в свой индекс, затем сюда: внутренняя метка
имеет приоритет над торговым кодом при коллизии.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import UniqueViolationError

from core.errors.boundary import PlatformConflictError
from core.models.platform_model import PlatformModel
from core.utils.ids import new_id
from core.utils.time import utcnow


class CatalogBarcode(PlatformModel):
    """Торговый код → товар/упаковка. Таблица ``catalog_barcodes`` (shared)."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "catalog_barcodes"
        indexes: list[Index] = [
            Index(["company_id", "barcode"], unique=True),
            Index(["company_id", "product_id"]),
        ]

    barcode_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    barcode: str = DbField(max_length=128)
    product_id: str = DbField(max_length=64)
    uom_id: str | None = DbField(default=None, max_length=64)
    """Упаковка (``catalog_uoms.uom_id``) либо NULL — код самого товара."""
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
        product_id: str,
        uom_id: str | None = None,
    ) -> Self:
        """Привязать код к товару/упаковке — единственная точка записи.

        ``unique (company_id, barcode)`` — один код = один носитель.
        Повторная привязка того же кода к тому же носителю — no-op;
        к другому — ``barcode_conflict``.
        """
        code = barcode.strip()
        if not code:
            raise PlatformConflictError(
                "Barcode must be non-empty", error_code="barcode_empty"
            )
        existing = await cls.resolve(company_id, code)
        if existing is not None:
            if existing.product_id == product_id and existing.uom_id == uom_id:
                return existing
            raise PlatformConflictError(
                "Barcode is already bound to another entity",
                error_code="barcode_conflict",
            )
        try:
            return await cls.create(
                cls(
                    barcode_id=new_id("cbc"),
                    company_id=company_id,
                    barcode=code,
                    product_id=product_id,
                    uom_id=uom_id,
                    created_at=utcnow(),
                )
            )
        except UniqueViolationError as exc:
            raise PlatformConflictError(
                "Barcode is already bound to another entity",
                error_code="barcode_conflict",
            ) from exc

    @classmethod
    async def resolve(cls, company_id: str, barcode: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, barcode=barcode
        ).get_or_none()

    @classmethod
    async def list_by_product_by_barcode_asc(cls, company_id: str, product_id: str) -> list[Self]:
        """Все коды товара и его упаковок, ORDER BY barcode ASC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).order_by("barcode").all()

    @classmethod
    async def list_by_products_by_barcode_asc(
        cls, company_id: str, product_ids: list[str]
    ) -> list[Self]:
        """Коды пачки товаров одним запросом — для списочных view.

        ``ORDER BY barcode ASC``. Предела нет.
        """
        if not product_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id, product_id__in=product_ids
        ).order_by("barcode").all()

    @classmethod
    async def release_entity(cls, company_id: str, product_id: str) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).delete()

    @classmethod
    async def release_uom(cls, company_id: str, uom_id: str) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, uom_id=uom_id
        ).delete()

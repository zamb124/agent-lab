"""Штрихкоды склада: единая точка уникальности `StockBarcodeIndex`."""

from __future__ import annotations

from oxyde.exceptions import UniqueViolationError

from apps.stock.models import StockBarcodeEntityType, StockBarcodeIndex
from apps.stock.services.ids import new_id
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.utils.time import utcnow


class StockBarcodeResolveResult:
    """Результат `stock/barcode/resolve`: тип носителя и его id."""

    def __init__(self, entity_type: StockBarcodeEntityType, entity_id: str) -> None:
        self.entity_type: StockBarcodeEntityType = entity_type
        self.entity_id: str = entity_id


class BarcodeService:
    """Регистрация и resolve штрихкодов. `unique (company_id, barcode)` — атомарность."""

    async def register(
        self,
        *,
        company_id: str,
        barcode: str,
        entity_type: StockBarcodeEntityType,
        entity_id: str,
    ) -> StockBarcodeIndex:
        code = barcode.strip()
        if not code:
            raise PlatformConflictError(
                "Barcode must be non-empty", error_code="barcode_empty"
            )
        existing = await StockBarcodeIndex.resolve(company_id, code)
        if existing is not None:
            if existing.entity_id == entity_id and existing.entity_type == entity_type:
                return existing
            raise PlatformConflictError(
                "Barcode is already bound to another entity",
                error_code="barcode_conflict",
            )
        entry = StockBarcodeIndex(
            barcode_id=new_id("bcd"),
            company_id=company_id,
            barcode=code,
            entity_type=entity_type,
            entity_id=entity_id,
            created_at=utcnow(),
        )
        try:
            return await StockBarcodeIndex.objects.create(instance=entry)
        except UniqueViolationError as exc:
            raise PlatformConflictError(
                "Barcode is already bound to another entity",
                error_code="barcode_conflict",
            ) from exc

    async def replace(
        self,
        *,
        company_id: str,
        barcode: str | None,
        entity_type: StockBarcodeEntityType,
        entity_id: str,
    ) -> None:
        """Перепривязка кода сущности: старые записи entity снимаются, новая пишется."""
        await StockBarcodeIndex.release_entity(company_id, entity_id)
        if barcode is not None and barcode.strip() != "":
            _ = await self.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=entity_type,
                entity_id=entity_id,
            )

    async def resolve(
        self, *, company_id: str, barcode: str
    ) -> StockBarcodeResolveResult:
        entry = await StockBarcodeIndex.resolve(company_id, barcode.strip())
        if entry is None:
            raise PlatformNotFoundError(
                "Barcode not found", error_code="barcode_not_found"
            )
        return StockBarcodeResolveResult(entry.entity_type, entry.entity_id)

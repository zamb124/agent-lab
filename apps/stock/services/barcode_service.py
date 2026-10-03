"""Штрихкоды склада: единая точка уникальности `StockBarcodeIndex` + GS1."""

from __future__ import annotations

from apps.stock.models import (
    StockBarcodeEntityType,
    StockBarcodeIndex,
    StockLot,
)
from apps.stock.models.gs1 import Gs1Barcode, parse_gs1
from core.errors.boundary import PlatformNotFoundError


class StockBarcodeResolveResult:
    """Результат `stock/barcode/resolve`: тип носителя, его id и GS1-разбор."""

    def __init__(
        self,
        entity_type: StockBarcodeEntityType,
        entity_id: str,
        parsed: Gs1Barcode,
    ) -> None:
        self.entity_type: StockBarcodeEntityType = entity_type
        self.entity_id: str = entity_id
        self.parsed: Gs1Barcode = parsed


class BarcodeService:
    """Регистрация и resolve штрихкодов. `unique (company_id, barcode)` — атомарность.

    ``stock_barcodes`` — единственный источник истины для сканируемых
    кодов: доменные сущности своих barcode-полей не хранят. Resolve:
    сырая строка в индексе → GS1-семантика (GTIN → товар/упаковка,
    SSCC → контейнер/локация, serial/lot → партия внутри товара) →
    извлечённые AI как отдельные записи индекса.
    """

    async def register(
        self,
        *,
        company_id: str,
        barcode: str,
        entity_type: StockBarcodeEntityType,
        entity_id: str,
    ) -> StockBarcodeIndex:
        """Привязать штрихкод к сущности в индексе.

        ``unique (company_id, barcode)`` — один код = один носитель:
        один и тот же штрихкод не может быть и товаром, и ячейкой.
        Повторная регистрация того же кода на ту же сущность — no-op;
        на другую — ``barcode_conflict``.
        """
        return await StockBarcodeIndex.bind(
            company_id=company_id,
            barcode=barcode,
            entity_type=entity_type,
            entity_id=entity_id,
        )

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
        """Что отсканировал оператор — «расшифровать код до сущности».

        Оператор сканирует наклейку — система отвечает «это паллета
        PLT-012» или «это партия LOT-55 товара мука». Порядок важен:

        1. Сырая строка в индексе — если код зарегистрирован
           напрямую (например, код ячейки), берём его;
        2. GS1-семантика — GTIN + lot/serial резолвится в партию,
           потому что «код с серийником» конкретнее, чем просто товар;
        3. Извлечённые AI в индексе — когда SSCC/GTIN хранится
           отдельной записью.

        Не найдено → ``barcode_not_found``.
        """
        code = barcode.strip()
        parsed = parse_gs1(code)
        entry = await StockBarcodeIndex.resolve(company_id, code)
        if entry is not None:
            return StockBarcodeResolveResult(
                entry.entity_type, entry.entity_id, parsed
            )
        if parsed.is_gs1:
            result = await self._resolve_gs1(company_id, parsed)
            if result is not None:
                return result
            result = await self._resolve_extracted(company_id, parsed)
            if result is not None:
                return result
        raise PlatformNotFoundError(
            "Barcode not found", error_code="barcode_not_found"
        )

    async def _resolve_extracted(
        self, company_id: str, parsed: Gs1Barcode
    ) -> StockBarcodeResolveResult | None:
        """Индекс по извлечённым AI (sscc/gtin/serial/lot) — когда штрихкод
        зарегистрирован на сущности отдельной записью, а не полем barcode."""
        keys: list[str] = []
        for key in (
            parsed.sscc,
            parsed.gtin,
            parsed.serial,
            parsed.lot_name,
        ):
            if key and key not in keys:
                keys.append(key)
        for key in keys:
            entry = await StockBarcodeIndex.resolve(company_id, key)
            if entry is not None:
                return StockBarcodeResolveResult(
                    entry.entity_type, entry.entity_id, parsed
                )
        return None

    async def _resolve_gs1(
        self, company_id: str, parsed: Gs1Barcode
    ) -> StockBarcodeResolveResult | None:
        """Семантика AI: GTIN → товар/упаковка, SSCC → контейнер-локация,
        `lot_name`/`serial` → партия (по имени в рамках GTIN-товара).

        Все ключи смотрятся в одном индексе ``stock_barcodes``: GTIN
        записан на product или packaging, SSCC — на контейнер-локацию.
        Партия по имени ищется в рамках разрешённого GTIN-товара —
        «номер партии поставщика» уникален только внутри товара.
        """
        product_id: str | None = None
        if parsed.gtin:
            entry = await StockBarcodeIndex.resolve(company_id, parsed.gtin)
            if entry is not None and entry.entity_type == StockBarcodeEntityType.PRODUCT:
                product_id = entry.entity_id
                if not parsed.lot_name and not parsed.serial:
                    return StockBarcodeResolveResult(
                        StockBarcodeEntityType.PRODUCT, product_id, parsed
                    )
            elif entry is not None and entry.entity_type == StockBarcodeEntityType.PACKAGING:
                return StockBarcodeResolveResult(
                    StockBarcodeEntityType.PACKAGING,
                    entry.entity_id,
                    parsed,
                )
        if parsed.sscc:
            entry = await StockBarcodeIndex.resolve(company_id, parsed.sscc)
            if entry is not None and entry.entity_type in {
                StockBarcodeEntityType.CONTAINER,
                StockBarcodeEntityType.LOCATION,
            }:
                return StockBarcodeResolveResult(
                    entry.entity_type, entry.entity_id, parsed
                )
        for name in (parsed.serial, parsed.lot_name):
            if name and product_id is not None:
                lot = await StockLot.by_name(company_id, product_id, name)
                if lot is not None:
                    return StockBarcodeResolveResult(
                        StockBarcodeEntityType.LOT, lot.lot_id, parsed
                    )
        return None

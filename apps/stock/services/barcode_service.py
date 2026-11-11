"""Штрихкоды склада: логистический индекс `StockBarcodeIndex` + GS1.

Логистические метки (ячейки, контейнеры, партии, накладные, ресурсы)
живут в ``stock_barcodes`` и биндятся внутри lane-транзакций. Торговые
коды (GTIN товара, коды упаковок) — в ``catalog_barcodes`` (shared):
resolve смотрит сначала свой индекс, затем каталог — внутренняя метка
имеет приоритет над торговым кодом.
"""

from __future__ import annotations

from apps.stock.models import (
    StockBarcodeEntityType,
    StockBarcodeIndex,
    StockLot,
)
from apps.stock.models.gs1 import Gs1Barcode, parse_gs1
from core.catalog.models import CatalogBarcode
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

    ``stock_barcodes`` — индекс складских носителей: логистические
    сущности своих barcode-полей не хранят. Торговый код регистрируется
    через ``CatalogService.bind_barcode`` и попадает в
    ``catalog_barcodes``. Resolve: сырая строка в складском индексе →
    сырая строка в каталоге → GS1-семантика (GTIN → товар/упаковка
    каталога, SSCC → контейнер/локация, serial/lot → партия внутри
    товара) → извлечённые AI как отдельные записи обоих индексов.
    """

    async def register(
        self,
        *,
        company_id: str,
        barcode: str,
        entity_type: StockBarcodeEntityType,
        entity_id: str,
    ) -> StockBarcodeIndex:
        """Привязать логистический код к сущности в индексе.

        ``unique (company_id, barcode)`` — один код = один носитель.
        Повторная регистрация того же кода на ту же сущность — no-op;
        на другую — ``barcode_conflict``. Торговые коды (товар и
        упаковки) сюда не идут — только через каталог.
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

        1. Сырая строка в складском индексе — внутренняя метка
           (например, код ячейки) сильнее торгового кода;
        2. Сырая строка в ``catalog_barcodes`` — торговый код товара
           или упаковки;
        3. GS1-семантика — GTIN + lot/serial резолвится в партию,
           потому что «код с серийником» конкретнее, чем просто товар;
        4. Извлечённые AI в обоих индексах — когда SSCC/GTIN хранится
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
        catalog_hit = _catalog_result(
            await CatalogBarcode.resolve(company_id, code), parsed
        )
        if catalog_hit is not None:
            return catalog_hit
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
        """Индексы по извлечённым AI (sscc/gtin/serial/lot): складской, затем каталог."""
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
            catalog_hit = _catalog_result(
                await CatalogBarcode.resolve(company_id, key), parsed
            )
            if catalog_hit is not None:
                return catalog_hit
        return None

    async def _resolve_gs1(
        self, company_id: str, parsed: Gs1Barcode
    ) -> StockBarcodeResolveResult | None:
        """Семантика AI: GTIN → товар/упаковка каталога, SSCC → контейнер-локация,
        `lot_name`/`serial` → партия (по имени в рамках GTIN-товара).

        GTIN ищется в ``catalog_barcodes``: ``uom_id`` задан — код
        упаковки, иначе код самого товара. SSCC — только складская
        метка, в ``stock_barcodes``. Партия по имени ищется в рамках
        разрешённого GTIN-товара — «номер партии поставщика» уникален
        только внутри товара.
        """
        product_id: str | None = None
        if parsed.gtin:
            entry = await CatalogBarcode.resolve(company_id, parsed.gtin)
            if entry is not None and entry.uom_id is None:
                product_id = entry.product_id
                if not parsed.lot_name and not parsed.serial:
                    return StockBarcodeResolveResult(
                        StockBarcodeEntityType.PRODUCT, product_id, parsed
                    )
            elif entry is not None:
                return StockBarcodeResolveResult(
                    StockBarcodeEntityType.PACKAGING,
                    entry.uom_id or "",
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
                lot = await StockLot.by_product_and_name(company_id, product_id, name)
                if lot is not None:
                    return StockBarcodeResolveResult(
                        StockBarcodeEntityType.LOT, lot.lot_id, parsed
                    )
        return None


def _catalog_result(
    entry: CatalogBarcode | None, parsed: Gs1Barcode
) -> StockBarcodeResolveResult | None:
    """Хит торгового кода → результат скана: товар или упаковка."""
    if entry is None:
        return None
    if entry.uom_id is not None:
        return StockBarcodeResolveResult(
            StockBarcodeEntityType.PACKAGING, entry.uom_id, parsed
        )
    return StockBarcodeResolveResult(
        StockBarcodeEntityType.PRODUCT, entry.product_id, parsed
    )

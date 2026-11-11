"""Складской фасет каталога: учётная политика товаров + партии.

``stock_products`` — фасет: базовые атрибуты (имя/SKU/ЕИ/габариты)
живут в едином каталоге ``core/catalog``; здесь только складская
политика (tracking, метод оценки, сроки, стратегия отбора) и
складские партии/серийники (``stock_lots``). ``StockCatalogService``
оркестрирует обе стороны: создание позиции = карточка в каталоге +
строка фасета, чтение = фасет + резолв эффективных полей в scope
``stock``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from oxyde.exceptions import UniqueViolationError

from apps.stock.models import (
    StockBarcodeEntityType,
    StockLot,
    StockProduct,
    StockRemovalStrategy,
    StockTracking,
    ValuationMethod,
)
from apps.stock.models.api import StockProductView
from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.ids import new_id
from core.catalog.contracts import (
    CatalogOverlay,
    CatalogScope,
    ResolvedProduct,
)
from core.catalog.events import publish_catalog_product_facet_changed
from core.catalog.models import CatalogBarcode
from core.catalog.service import CatalogService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.pagination import OffsetPage
from core.utils.time import utcnow

STOCK_FACET = "stock"
STOCK_SCOPES: list[CatalogScope] = [CatalogScope(facet=STOCK_FACET)]
"""Цепочка резолва склада: у сервиса нет экземпляров — один уровень."""


def _not_found(message: str, error_code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=error_code)


def _conflict(message: str, error_code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=error_code)


class StockCatalogService:
    """Сценарии складского каталога: фасет товара + партии.

    Базовые поля товара, ЕИ/упаковки и торговые штрихкоды живут в
    ``CatalogService`` (shared); этот сервис добавляет складскую
    политику и собирает ``StockProductView`` — плоскую форму
    «карточка + политика», которую видит складской UI.
    """

    def __init__(self, catalog: CatalogService, barcode: BarcodeService) -> None:
        self._catalog: CatalogService = catalog
        self._barcode: BarcodeService = barcode

    # --- Products ---

    async def create_product(
        self,
        *,
        company_id: str,
        name: str,
        sku: str | None,
        uom_id: str,
        valuation_method: ValuationMethod,
        standard_price: Decimal,
        tracking: StockTracking,
        is_storable: bool,
        category: str,
        barcodes: list[str] | None = None,
        product_id: str | None = None,
        weight: Decimal | None = None,
        volume: Decimal | None = None,
        use_expiration: bool = False,
        expiration_days: int | None = None,
        best_before_days: int | None = None,
        removal_days: int | None = None,
        alert_days: int | None = None,
        removal_strategy: StockRemovalStrategy | None = None,
    ) -> StockProductView:
        """Завести товар на складе: карточка каталога + складской фасет.

        ``product_id`` — подключить существующий товар каталога
        («такой уже есть» из дедуп-подсказки); иначе создаётся новая
        мастер-карта. Фасет держит только учётную политику.
        Дубль фасета → ``product_facet_conflict``; дубль SKU — из
        каталога (``sku_conflict``).
        """
        if product_id is None:
            product = await self._catalog.create_product(
                company_id=company_id,
                name=name,
                uom_id=uom_id,
                sku=sku,
                weight=weight,
                volume=volume,
                barcodes=barcodes,
            )
            product_id = product.product_id
        else:
            product = await self._catalog.get_product(
                company_id=company_id, product_id=product_id
            )
        now = utcnow()
        try:
            _ = await StockProduct.create(StockProduct(
                    product_id=product_id,
                    company_id=company_id,
                    tracking=tracking,
                    is_storable=is_storable,
                    category=category,
                    valuation_method=valuation_method,
                    standard_price=standard_price,
                    use_expiration=use_expiration,
                    expiration_days=expiration_days,
                    best_before_days=best_before_days,
                    removal_days=removal_days,
                    alert_days=alert_days,
                    removal_strategy=removal_strategy,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict(
                "Product is already managed by stock",
                "product_facet_conflict",
            ) from exc
        await publish_catalog_product_facet_changed(
            product_id, company_id, facet=STOCK_FACET
        )
        return await self.get_product(company_id=company_id, product_id=product_id)

    async def update_product(
        self,
        *,
        company_id: str,
        product_id: str,
        barcodes: list[str] | None = None,
        is_active: bool | None = None,
        valuation_method: ValuationMethod | None = None,
        standard_price: Decimal | None = None,
        tracking: StockTracking | None = None,
        category: str | None = None,
        overlay: CatalogOverlay | None = None,
        use_expiration: bool | None = None,
        expiration_days: int | None = None,
        best_before_days: int | None = None,
        removal_days: int | None = None,
        alert_days: int | None = None,
        removal_strategy: StockRemovalStrategy | None = None,
    ) -> StockProductView:
        """Править складскую политику товара и его overlay scope ``stock``.

        Смена ``valuation_method`` проходит через
        ``StockProduct.update_valuation_method`` — там проверка,
        что по товару ещё нет слоёв оценки. ``overlay`` — PUT-форма
        складских переопределений контента (имя/описание/галерея в
        складских документах); базовые поля правятся только через
        мастер-карту (``catalog_products/*``).
        """
        facet = await StockProduct.by_id(company_id, product_id)
        if facet is None:
            raise _not_found("Product not found", "product_not_found")
        facet_changed = False
        if valuation_method is not None or standard_price is not None:
            facet = await StockProduct.update_valuation_method(
                company_id=company_id,
                product_id=product_id,
                valuation_method=valuation_method or facet.valuation_method,
                standard_price=standard_price,
            )
            facet_changed = True
        changed = False
        if tracking is not None:
            facet.tracking = tracking
            changed = True
        if category is not None:
            facet.category = category
            changed = True
        if use_expiration is not None:
            facet.use_expiration = use_expiration
            changed = True
        if expiration_days is not None:
            facet.expiration_days = expiration_days
            changed = True
        if best_before_days is not None:
            facet.best_before_days = best_before_days
            changed = True
        if removal_days is not None:
            facet.removal_days = removal_days
            changed = True
        if alert_days is not None:
            facet.alert_days = alert_days
            changed = True
        if removal_strategy is not None:
            facet.removal_strategy = removal_strategy
            changed = True
        if is_active is not None:
            facet.is_active = is_active
            changed = True
        if changed:
            facet.updated_at = utcnow()
            _ = await facet.save()
            facet_changed = True
        if overlay is not None:
            _ = await self._catalog.set_overlay(
                company_id=company_id,
                product_id=product_id,
                scope=STOCK_SCOPES[0],
                overlay=overlay,
                resolve_scopes=STOCK_SCOPES,
            )
        if barcodes is not None:
            await self._catalog.replace_product_barcodes(
                company_id=company_id, product_id=product_id, barcodes=barcodes
            )
        if facet_changed:
            await publish_catalog_product_facet_changed(
                product_id, company_id, facet=STOCK_FACET
            )
        return await self.get_product(company_id=company_id, product_id=product_id)

    async def get_product(
        self, *, company_id: str, product_id: str
    ) -> StockProductView:
        facet = await StockProduct.by_id(company_id, product_id)
        if facet is None:
            raise _not_found("Product not found", "product_not_found")
        resolved = await self._catalog.resolve(
            company_id=company_id, product_id=product_id, scopes=STOCK_SCOPES
        )
        codes = await CatalogBarcode.list_by_products_by_barcode_asc(
            company_id, [product_id]
        )
        return _to_view(facet, resolved, _product_codes(codes))

    async def list_products(
        self, *, company_id: str, limit: int, offset: int
    ) -> OffsetPage[StockProductView]:
        facets = await StockProduct.list_page_by_created_desc(
            company_id, limit=limit, offset=offset
        )
        total = await StockProduct.count_for_company(company_id)
        product_ids = [row.product_id for row in facets]
        resolved = await self._catalog.resolve_many(
            company_id=company_id,
            product_ids=product_ids,
            scopes=STOCK_SCOPES,
        )
        codes = await CatalogBarcode.list_by_products_by_barcode_asc(
            company_id, product_ids
        )
        codes_by_product: dict[str, list[CatalogBarcode]] = {}
        for code in codes:
            codes_by_product.setdefault(code.product_id, []).append(code)
        return OffsetPage(
            items=[
                _to_view(
                    row,
                    resolved[row.product_id],
                    _product_codes(codes_by_product.get(row.product_id, [])),
                )
                for row in facets
                if row.product_id in resolved
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    # --- Lots ---

    async def create_lot(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str,
        barcode: str | None,
        expiration_at: datetime | None,
    ) -> StockLot:
        """Зарегистрировать партию/серийный номер товара в справочнике.

        ``name`` — номер партии поставщика («2024-08-15, смена 2») или
        серийный номер для ``tracking=serial``; ``expiration_at`` —
        срок годности. Из него по дневным смещениям фасета выводятся
        производные даты (как в Odoo): ``removal_at`` — не позже этой
        даты отбирать (``expiration − removal_days``, FEFO смотрит
        именно сюда), ``best_before_at`` — «лучше до»
        (``expiration − best_before_days``), ``alert_at`` — дата
        предупреждения (``expiration − alert_days``). Без смещений
        производные равны самому ``expiration_at``.
        Дубль ``name`` на пару (продукт, компания) → ``lot_conflict``.
        """
        facet = await StockProduct.by_id(company_id, product_id)
        if facet is None:
            raise _not_found("Product not found", "product_not_found")
        removal_at = best_before_at = alert_at = None
        if expiration_at is not None:
            # Смещения фасета сдвигают даты РАНЬШЕ срока годности:
            # отгружать и предупреждать надо до того, как партия испортится.
            removal_at = expiration_at - timedelta(
                days=facet.removal_days or 0
            )
            best_before_at = expiration_at - timedelta(
                days=facet.best_before_days or 0
            )
            alert_at = expiration_at - timedelta(
                days=facet.alert_days or 0
            )
        try:
            lot = await StockLot.create(StockLot(
                    lot_id=new_id("lot"),
                    company_id=company_id,
                    product_id=product_id,
                    name=name,
                    expiration_at=expiration_at,
                    best_before_at=best_before_at,
                    removal_at=removal_at,
                    alert_at=alert_at,
                    created_at=utcnow(),
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("Lot name already exists", "lot_conflict") from exc
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.LOT,
                entity_id=lot.lot_id,
            )
        return lot

    async def list_lots(
        self, *, company_id: str, product_id: str | None
    ) -> list[StockLot]:
        return await StockLot.list_by_name_asc(company_id, product_id=product_id)


def _product_codes(codes: list[CatalogBarcode]) -> list[str]:
    """Штрихкоды самого товара (без кодов упаковок), ASC."""
    return [c.barcode for c in codes if c.uom_id is None]


def _to_view(
    facet: StockProduct,
    resolved: ResolvedProduct,
    barcodes: list[str],
) -> StockProductView:
    """Фасет + резолв каталога → плоская карточка складского API."""
    product = resolved.product
    return StockProductView(
        product_id=facet.product_id,
        name=resolved.name,
        description=resolved.description,
        image_file_ids=resolved.image_file_ids,
        sources=resolved.sources,
        sku=product.sku,
        uom_id=product.uom_id,
        barcodes=barcodes,
        weight=product.weight,
        volume=product.volume,
        is_archived=product.is_archived,
        tracking=facet.tracking,
        is_storable=facet.is_storable,
        is_active=facet.is_active,
        category=facet.category,
        valuation_method=facet.valuation_method,
        standard_price=facet.standard_price,
        use_expiration=facet.use_expiration,
        expiration_days=facet.expiration_days,
        best_before_days=facet.best_before_days,
        removal_days=facet.removal_days,
        alert_days=facet.alert_days,
        removal_strategy=facet.removal_strategy,
        created_at=facet.created_at,
        updated_at=facet.updated_at,
    )

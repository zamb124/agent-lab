"""Каталог товаров: SKU, единицы измерения, фасовки, партии.

Агрегат «что храним»: карточка товара с методом оценки и политикой
учёта, базовая ЕИ и товарные упаковки (AUoM — строки ``stock_uom`` с
``product_id``), партии/серийники (``stock_lots``). Это справочные
записи: они не двигают количество и не пишут слоёв оценки — любое
изменение физического запаса идёт только через lane-методы моделей.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from oxyde.exceptions import UniqueViolationError

from apps.stock.models import (
    StockBarcodeEntityType,
    StockBarcodeIndex,
    StockContainerType,
    StockLot,
    StockProduct,
    StockRemovalStrategy,
    StockTracking,
    UnitOfMeasure,
    ValuationMethod,
)
from apps.stock.models.api import StockPackagingView
from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.ids import new_id
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.pagination import OffsetPage
from core.utils.time import utcnow


def _not_found(message: str, error_code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=error_code)


def _conflict(message: str, error_code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=error_code)


class CatalogService:
    """Сценарии каталога: продукты, ЕИ/фасовки, партии.

    Создание и правка «карточек товара»: SKU с методом оценки и
    tracking-политикой, упаковки («короб по 24») как товарные UoM,
    партии и серийные номера. Методы не трогают остатки — только
    справочник, по которому потом идут движения.
    """

    def __init__(self, barcode: BarcodeService) -> None:
        self._barcode: BarcodeService = barcode

    # --- UoM ---

    async def list_uoms(self, *, company_id: str) -> list[UnitOfMeasure]:
        return await UnitOfMeasure.list_by_category_and_name_asc(company_id)

    # --- Products ---

    async def create_product(
        self,
        *,
        company_id: str,
        name: str,
        sku: str,
        uom_id: str,
        valuation_method: ValuationMethod,
        standard_price: Decimal,
        tracking: StockTracking,
        is_storable: bool,
        category: str,
        barcode: str | None,
        weight: Decimal | None = None,
        volume: Decimal | None = None,
        use_expiration: bool = False,
        expiration_days: int | None = None,
        best_before_days: int | None = None,
        removal_days: int | None = None,
        alert_days: int | None = None,
        removal_strategy: StockRemovalStrategy | None = None,
    ) -> StockProduct:
        """Завести товар: одна запись ``stock_products`` + штрихкод.

        Карточка хранит бизнес-правила в одной строке с SKU:

        * ``tracking`` — по штукам / по партиям / по серийникам;
        * ``valuation_method`` — ``standard`` / ``average`` / ``fifo`` /
          ``unvalued``: как бухгалтерия считает стоимость этого товара;
        * ``weight``/``volume`` — габариты базовой ЕИ для проверок
          ёмкости ячеек и грузоподъёмности ресурсов;
        * ``use_expiration`` + ``*_days`` — сроки годности для FEFO;
        * ``removal_strategy`` — переопределение порядка отбора
          именно для этого товара.

        ``sku`` уникален на компанию: дубль → ``sku_conflict``.
        ``barcode`` регистрируется в ``stock_barcodes`` (индекс сканов).
        """
        if await UnitOfMeasure.by_id(company_id, uom_id) is None:
            raise _not_found("Unit of measure not found", "uom_not_found")
        now = utcnow()
        try:
            product = await StockProduct.create(StockProduct(
                    product_id=new_id("spr"),
                    company_id=company_id,
                    name=name,
                    sku=sku,
                    uom_id=uom_id,
                    tracking=tracking,
                    is_storable=is_storable,
                    category=category,
                    valuation_method=valuation_method,
                    standard_price=standard_price,
                    weight=weight,
                    volume=volume,
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
            raise _conflict("SKU already exists", "sku_conflict") from exc
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.PRODUCT,
                entity_id=product.product_id,
            )
        return product

    async def update_product(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str | None,
        sku: str | None,
        barcode: str | None,
        is_active: bool | None,
        valuation_method: ValuationMethod | None,
        standard_price: Decimal | None,
        tracking: StockTracking | None,
        category: str | None = None,
        weight: Decimal | None = None,
        volume: Decimal | None = None,
        use_expiration: bool | None = None,
        expiration_days: int | None = None,
        best_before_days: int | None = None,
        removal_days: int | None = None,
        alert_days: int | None = None,
        removal_strategy: StockRemovalStrategy | None = None,
    ) -> StockProduct:
        """Править карточку товара.

        Смена ``valuation_method`` проходит через
        ``StockProduct.update_valuation_method`` — там проверка,
        что по товару ещё нет слоёв оценки: менять способ оценки
        «задним числом» нельзя, история слоёв уже посчитана в одном
        методе и переоценивать её другим методом — ошибка учёта.

        Остальные поля правятся в той же строке ``stock_products``:
        карточка и SKU — одна запись.
        """
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        if valuation_method is not None or standard_price is not None:
            product = await StockProduct.update_valuation_method(
                company_id=company_id,
                product_id=product_id,
                valuation_method=valuation_method or product.valuation_method,
                standard_price=standard_price,
            )
        if name is not None:
            product.name = name
        if tracking is not None:
            product.tracking = tracking
        if category is not None:
            product.category = category
        if weight is not None:
            product.weight = weight
        if volume is not None:
            product.volume = volume
        if use_expiration is not None:
            product.use_expiration = use_expiration
        if expiration_days is not None:
            product.expiration_days = expiration_days
        if best_before_days is not None:
            product.best_before_days = best_before_days
        if removal_days is not None:
            product.removal_days = removal_days
        if alert_days is not None:
            product.alert_days = alert_days
        if removal_strategy is not None:
            product.removal_strategy = removal_strategy
        if sku is not None:
            product.sku = sku
        if is_active is not None:
            product.is_active = is_active
        if barcode is not None:
            _ = await self._barcode.replace(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.PRODUCT,
                entity_id=product.product_id,
            )
        product.updated_at = utcnow()
        try:
            _ = await product.save()
        except UniqueViolationError as exc:
            raise _conflict("SKU already exists", "sku_conflict") from exc
        return product

    async def get_product(
        self, *, company_id: str, product_id: str
    ) -> StockProduct:
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        return product

    async def list_products(
        self, *, company_id: str, limit: int, offset: int
    ) -> OffsetPage[StockProduct]:
        rows = await StockProduct.list_by_sku_asc(
            company_id, limit=limit, offset=offset
        )
        total = await StockProduct.count_for_company(company_id)
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

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
        срок годности. Из него по дневным смещениям карточки выводятся
        производные даты (как в Odoo): ``removal_at`` — не позже этой
        даты отбирать (``expiration − removal_days``, FEFO смотрит
        именно сюда), ``best_before_at`` — «лучше до»
        (``expiration − best_before_days``), ``alert_at`` — дата
        предупреждения (``expiration − alert_days``). Без смещений
        производные равны самому ``expiration_at``.
        Дубль ``name`` на пару (продукт, компания) → ``lot_conflict``.
        """
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        removal_at = best_before_at = alert_at = None
        if expiration_at is not None:
            # Смещения карточки сдвигают даты РАНЬШЕ срока годности:
            # отгружать и предупреждать надо до того, как партия испортится.
            removal_at = expiration_at - timedelta(
                days=product.removal_days or 0
            )
            best_before_at = expiration_at - timedelta(
                days=product.best_before_days or 0
            )
            alert_at = expiration_at - timedelta(
                days=product.alert_days or 0
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

    # --- Упаковки товаров (AUoM) ---

    @staticmethod
    async def _packaging_view(
        company_id: str, uom: UnitOfMeasure
    ) -> StockPackagingView:
        """Проекция строки ``stock_uom`` в «упаковку» — количество
        базовых единиц товара в одной упаковке (``factor / factor
        базовой ЕИ``)."""
        if uom.product_id is None:
            raise _conflict(
                "UoM row is not a product packaging",
                "packaging_not_product_uom",
            )
        product = await StockProduct.by_id(company_id, uom.product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        base = await UnitOfMeasure.by_id(company_id, product.uom_id)
        if base is None:
            raise _not_found(
                "Product base uom not found", "uom_not_found"
            )
        return StockPackagingView(
            packaging_id=uom.uom_id,
            product_id=uom.product_id,
            name=uom.name,
            quantity=uom.factor / base.factor,
            container_type_id=uom.container_type_id,
            weight=uom.weight,
            volume=uom.volume,
        )

    async def list_packagings(
        self, *, company_id: str, product_id: str | None
    ) -> list[StockPackagingView]:
        uoms = await UnitOfMeasure.list_packagings_by_product_id_and_factor_asc(company_id, product_id)
        if not uoms:
            return []
        products = await StockProduct.get_many(
            [uom.product_id or "" for uom in uoms]
        )
        bases = await UnitOfMeasure.get_many(
            [p.uom_id for p in products.values()]
        )
        views: list[StockPackagingView] = []
        for uom in uoms:
            product = (
                products.get(uom.product_id) if uom.product_id else None
            )
            base = (
                bases.get(product.uom_id) if product is not None else None
            )
            if product is None or base is None:
                raise _conflict(
                    "Packaging references missing product or uom",
                    "packaging_orphan",
                )
            views.append(
                StockPackagingView(
                    packaging_id=uom.uom_id,
                    product_id=uom.product_id or "",
                    name=uom.name,
                    quantity=uom.factor / base.factor,
                    container_type_id=uom.container_type_id,
                    weight=uom.weight,
                    volume=uom.volume,
                )
            )
        return views

    async def create_packaging(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str,
        quantity: Decimal,
        barcode: str | None,
        container_type_id: str | None,
        weight: Decimal | None,
        volume: Decimal | None,
    ) -> StockPackagingView:
        """Завести фасовку товара — «короб по 24 шт».

        Упаковка — это AUoM: строка ``stock_uom`` с ``product_id`` и
        ``factor = quantity × factor(базовой ЕИ товара)``, живущая в
        категории базовой ЕИ. Благодаря этому ``UnitOfMeasure.convert``
        сам переводит «3 коробки» в базовые единицы при проводке
        документа, а скан GTIN-14 короба даёт и товар, и количество.
        ``container_type_id`` связывает фасовку с принятой тарой —
        приёмка «по упаковке» создаст контейнер этого типа.
        """
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        base = await UnitOfMeasure.by_id(company_id, product.uom_id)
        if base is None:
            raise _not_found(
                "Product base uom not found", "uom_not_found"
            )
        if container_type_id is not None and (
            await StockContainerType.by_id(company_id, container_type_id) is None
        ):
            raise _not_found(
                "Container type not found", "container_type_not_found"
            )
        try:
            uom = await UnitOfMeasure.create(
                UnitOfMeasure(
                    uom_id=new_id("uom"),
                    company_id=company_id,
                    name=name,
                    category=base.category,
                    factor=quantity * base.factor,
                    product_id=product_id,
                    container_type_id=container_type_id,
                    weight=weight,
                    volume=volume,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict(
                "Packaging name already exists", "packaging_conflict"
            ) from exc
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.PACKAGING,
                entity_id=uom.uom_id,
            )
        return StockPackagingView(
            packaging_id=uom.uom_id,
            product_id=product_id,
            name=name,
            quantity=quantity,
            container_type_id=container_type_id,
            weight=weight,
            volume=volume,
        )

    async def delete_packaging(
        self, *, company_id: str, packaging_id: str
    ) -> StockPackagingView:
        """Удалить фасовку из справочника (штрихкод перестанет резолвиться)."""
        uom = await UnitOfMeasure.by_id(company_id, packaging_id)
        if uom is None or uom.product_id is None:
            raise _not_found("Packaging not found", "packaging_not_found")
        view = await self._packaging_view(company_id, uom)
        await StockBarcodeIndex.release_entity(company_id, packaging_id)
        await UnitOfMeasure.delete_uom(company_id, packaging_id)
        return view

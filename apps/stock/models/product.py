"""Складской фасет товара (stock_products) — учётная политика позиции.

``stock_products.product_id`` = ``catalog_products.product_id``: имя,
SKU, базовая ЕИ и габариты живут в едином каталоге (``core/catalog``,
shared). Здесь только складская политика: ``tracking`` (штуки/партии/
серийники), ``valuation_method`` + ``standard_price`` (как бухгалтерия
оценивает запас), сроки годности для FEFO и ``removal_strategy`` —
переопределение порядка отбора именно для этого товара. Все остатки,
движения и слои оценки ссылаются на ``product_id`` — фасет без
каталожной карточки не существует.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic

from apps.stock.models.common import (
    MONEY_DB,
    STOCK_DB,
    stock_ledger_cursor,
)
from apps.stock.models.enums import (
    StockRemovalStrategy,
    StockTracking,
    ValuationMethod,
)
from apps.stock.models.value_layer import StockValueLayer
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import LaneCursor
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockProduct(PlatformModel):
    """Учётная политика товара на складе. Таблица ``stock_products``.

    * ``tracking`` — ``none`` (насыпной товар), ``lot`` (партии со
      сроками), ``serial`` (каждая единица — серийный номер, IMEI);
    * ``valuation_method`` — метод оценки запаса:
      ``standard`` — по карточной цене (разница уходит коррекцией),
      ``average`` — по скользящей средней, ``fifo`` — послойно,
      ``unvalued`` — не оцениваем (только количество);
    * ``standard_price`` — карточная цена базовой ЕИ;
    * ``use_expiration`` + ``*_days`` — сроки годности для FEFO-отбора;
    * ``removal_strategy`` — переопределение порядка отбора над
      типом хранения и складом;
    * ``category`` — фильтр putaway-правил (складская категория,
      не каталог).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_products"
        indexes: list[Index] = [
            Index(["company_id", "product_id"]),
        ]

    product_id: str = DbField(db_pk=True, max_length=64)
    """``catalog_products.product_id`` — единый идентификатор товара."""
    company_id: str = DbField(max_length=100)
    tracking: StockTracking = DbField(default=StockTracking.NONE)
    is_storable: bool = DbField(default=True)
    is_active: bool = DbField(default=True)
    category: str = DbField(default="", max_length=128)
    valuation_method: ValuationMethod = DbField()
    standard_price: Decimal = DbField(default=Decimal("0"), db_type=MONEY_DB)
    use_expiration: bool = DbField(default=False)
    expiration_days: int | None = DbField(default=None)
    best_before_days: int | None = DbField(default=None)
    removal_days: int | None = DbField(default=None)
    alert_days: int | None = DbField(default=None)
    removal_strategy: StockRemovalStrategy | None = DbField(default=None)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, product_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).get_or_none()

    @classmethod
    async def found_in_company_by_ids(cls, company_id: str, product_ids: list[str]) -> dict[str, Self]:
        """Найденные фасеты компании по id. Пустой список — {}. Отсутствующие id не входят."""
        if not product_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, product_id__in=product_ids
        ).all()
        return {row.product_id: row for row in rows}

    @classmethod
    async def list_page_by_created_desc(
        cls, company_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        """Окно фасетов компании, ORDER BY created_at DESC, product_id ASC, limit и offset."""
        return await cls.objects.filter(company_id=company_id).order_by(
            "-created_at", "product_id"
        ).limit(limit).offset(offset).all()

    @classmethod
    async def count_for_company(cls, company_id: str) -> int:
        return await cls.objects.filter(company_id=company_id).count()

    @classmethod
    async def update_valuation_method(
        cls,
        *,
        company_id: str,
        product_id: str,
        valuation_method: ValuationMethod,
        standard_price: Decimal | None,
    ) -> Self:
        """Смена метода оценки товара. Запрещена при наличии слоёв.

        Если по товару уже прошли проводки (в ``stock_value_layers``
        есть строки по этому ``product_id``), метод заперт — история
        слоёв посчитана в одном методе и переоценивать её задним
        числом другим методом нельзя: ``valuation_method_locked``.

        ``LaneCursor.lock`` по курсору журнала ждёт незакоммиченных
        писателей слоёв: проверка ``exists_for_products`` видит только
        зафиксированный журнал, и смена метода сериализуется с ними.
        """
        async with atomic(using=STOCK_DB):
            await LaneCursor.lock(
                stock_ledger_cursor(company_id), company_id=company_id, using=STOCK_DB
            )
            product = await cls.objects.filter(
                company_id=company_id, product_id=product_id
            ).for_update().get_or_none()
            if product is None:
                raise PlatformNotFoundError(
                    "Product not found", error_code="product_not_found"
                )
            if product.valuation_method != valuation_method:
                has_layers = await StockValueLayer.exists_for_products(
                    company_id, [product_id]
                )
                if has_layers:
                    raise PlatformConflictError(
                        "Valuation method is locked by existing layers",
                        error_code="valuation_method_locked",
                    )
            product.valuation_method = valuation_method
            if standard_price is not None:
                product.standard_price = standard_price
            product.updated_at = utcnow()
            _ = await product.save()
            return product

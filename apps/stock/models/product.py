"""Товары каталога (stock_products) — карточка складской позиции.

«Продукт» — конкретная складская позиция и одновременно её
бизнес-карточка: SKU и штрихкод, как отслеживается (``tracking`` —
по штукам/по партиям/по серийникам), как оценивается
(``valuation_method`` — стандартная цена / средняя / FIFO), габариты
базовой единицы и сроки годности. Все остатки, движения и записи
оценки ссылаются на ``product_id``.

Шаблонов и вариантов нет: одна позиция = одна строка. Если бизнесу
понадобится «красная/синяя футболка одной модели» — это две позиции
с разными SKU, а не варианты общего шаблона.
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
    STOCK_ZERO,
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
    """Карточка товара и конкретный SKU. Таблица ``stock_products``.

    Бизнес-поля (читаются бухгалтерией и складом):

    * ``name``, ``sku``, ``uom_id`` — «что это» и в чём
      измеряется базово (штуки/кг/литры);
    * ``tracking`` — ``none`` (насыпной товар), ``lot`` (партии со
      сроками), ``serial`` (каждая единица — серийный номер, IMEI);
    * ``valuation_method`` — метод оценки запаса:
      ``standard`` — по карточной цене (разница уходит коррекцией),
      ``average`` — по скользящей средней, ``fifo`` — послойно
      (какой слой пришёл раньше, тот и списывается первым),
      ``unvalued`` — не оцениваем (только количество);
    * ``standard_price`` — карточная цена базовой ЕИ для ``standard``/
      ``average`` и стартовая точка оценки;
    * ``weight``/``volume`` — вес/объём базовой ЕИ: проверки ёмкости
      ячеек и грузоподъёмности ресурсов считают по ним;
    * ``use_expiration`` + ``*_days`` — сроки годности для FEFO-отбора
      и просрочки («best_before» — «лучше до», «removal» — «убрать с
      полки до»);
    * ``removal_strategy`` — переопределение порядка отбора именно для
      этого товара (над типом хранения и складом).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_products"
        indexes: list[Index] = [
            Index(["company_id", "sku"], unique=True),
        ]

    product_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    name: str = DbField(max_length=255)
    sku: str = DbField(max_length=128)
    uom_id: str = DbField(max_length=64)
    tracking: StockTracking = DbField(default=StockTracking.NONE)
    is_storable: bool = DbField(default=True)
    is_active: bool = DbField(default=True)
    category: str = DbField(default="", max_length=128)
    valuation_method: ValuationMethod = DbField()
    standard_price: Decimal = DbField(default=STOCK_ZERO, db_type=MONEY_DB)
    weight: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    """Вес базовой ЕИ (кг) — для проверок ёмкости и грузоподъёмности."""
    volume: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    """Объём базовой ЕИ — по конвенции каталога."""
    use_expiration: bool = DbField(default=False)
    expiration_days: int | None = DbField(default=None)
    best_before_days: int | None = DbField(default=None)
    removal_days: int | None = DbField(default=None)
    alert_days: int | None = DbField(default=None)
    removal_strategy: StockRemovalStrategy | None = DbField(default=None)
    """Переопределение стратегии отбора над типом хранения и складом."""
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
        """Найденные товары компании по id. Пустой список — {}. Отсутствующие id не входят. Порядка нет."""
        if not product_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, product_id__in=product_ids
        ).all()
        return {row.product_id: row for row in rows}

    @classmethod
    async def list_by_sku_asc(
        cls, company_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        """Окно товаров компании, ORDER BY sku ASC, limit и offset."""
        return await cls.objects.filter(company_id=company_id).order_by("sku").limit(
            limit
        ).offset(offset).all()

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

        Пример: карточка муки была ``standard`` 40 ₽, бухгалтерия
        переводит её на ``average``. Если по муке уже прошли проводки
        (в ``stock_value_layers`` есть строки по этому ``product_id``),
        метод заперт — история слоёв посчитана в одном методе и
        переоценивать её задним числом другим методом нельзя:
        ``valuation_method_locked``.

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

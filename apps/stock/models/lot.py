"""Партии и серийные номера (stock_lots).

«Партия» — след прослеживаемости товара: номер серии у поставщика,
дата производства, срок годности. Одна и та же мука двух разных
производителей — это два продукта каталога, но одна и та же мука двух
разных суток — один продукт и две партии.

Партия существует, чтобы ответить на вопросы «эта единица от какого
завода?», «какой у неё срок годности?», «кого отзываем при браке?».
Серийный номер — предельный случай партии размером в одну штуку
(tracking=serial): каждая единица товара прослеживается отдельно.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import STOCK_DB
from core.models.platform_model import PlatformModel


class StockLot(PlatformModel):
    """Партия/серийный номер продукта. Таблица ``stock_lots``.

    ``name`` — номер партии поставщика или сам серийный номер
    (для ``tracking=serial``). Поля ``expiration_date``/``removal_date``
    — сроки годности: FEFO-стратегия отбора берёт раньше те партии, у
    которых раньше ``removal_date``, а просроченный товар по
    ``expiration_date`` запрещён к отгрузке.

    Для серийных номеров при проводке строка блокируется
    (``by_id_locked``) и инвариант «суммарный остаток серийника ≤ 1»
    проверяется под блокировкой — одна и та же единица не может
    оказаться на складе дважды.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_lots"
        indexes: list[Index] = [
            Index(["company_id", "product_id", "name"], unique=True),
        ]

    lot_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    product_id: str = DbField(max_length=64)
    name: str = DbField(max_length=128)
    expiration_at: datetime | None = DbField(default=None)
    best_before_at: datetime | None = DbField(default=None)
    removal_at: datetime | None = DbField(default=None)
    """Не позже этой даты отбирать (FEFO денормализуется на `StockQuant`)."""
    alert_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, lot_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, lot_id=lot_id
        ).get_or_none()

    @classmethod
    async def by_id_locked(cls, company_id: str, lot_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, lot_id=lot_id
        ).for_update().get_or_none()


    @classmethod
    async def by_product_and_name(
        cls, company_id: str, product_id: str, name: str
    ) -> Self | None:
        """Партия компании по product_id и name. Нет строки — None."""
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id, name=name
        ).get_or_none()

    @classmethod
    async def list_by_name_asc(
        cls, company_id: str, *, product_id: str | None
    ) -> list[Self]:
        """Партии компании, ORDER BY name ASC, без предела. product_id None не фильтрует."""
        query = cls.objects.filter(company_id=company_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        return await query.order_by("name").all()

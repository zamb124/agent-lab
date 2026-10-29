"""Типы контейнеров (stock_container_types) — «виды тары» склада.

Контейнер — физическая тара, в которой хранят и возят товар: паллета,
короб, мешок, тоут, тележка. Этот справочник описывает тип («евро-
паллета 1200×800», «короб 60×40×40»), а не конкретную паллету —
конкретные экземпляры это локации ``usage=container``.

Заменяет старую модель ``stock_package_types``: упаковка теперь —
локация-контейнер, а её вид — StockContainerType.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import MONEY_DB, STOCK_DB
from apps.stock.models.enums import StockContainerKind
from core.models.platform_model import PlatformModel


class StockContainerType(PlatformModel):
    """Вид тары (паллета/короб/тоут...). Таблица ``stock_container_types``.

    * ``kind`` — паллета/короб/мешок/тоут/тележка/другое.
    * ``max_weight``/``max_volume``/``length``/``width``/``height`` —
      грузоподъёмность и габариты тары: при размещении ячейка может
      проверять «влезет ли эта паллета по весу».
    * ``tare_weight`` — вес самой пустой тары (брутто − тара = нетто
      при взвешивании).
    * ``is_reusable`` — многоразовая ли тара: одноразовый мешок после
      отгрузки партнёру архивируется сам (``is_active=false``), тоут
      остаётся в обороте.
    * ``allowed_parent_type_ids`` — во что можно вкладывать этот тип:
      пусто — куда угодно; иначе «тоут нельзя поставить в короб».
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_container_types"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "name"], unique=True),
        ]

    container_type_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    name: str = DbField(max_length=128)
    kind: StockContainerKind = DbField(default=StockContainerKind.OTHER)
    max_weight: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    tare_weight: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    max_volume: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    length: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    width: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    height: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    is_reusable: bool = DbField(default=False)
    """Многоразовый (тоут/тележка): не архивируется после опустошения."""
    allowed_parent_type_ids: list[str] = DbField(default_factory=list)
    """Пусто — вложенность не ограничена; иначе типы контейнеров-родителей."""
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, container_type_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, container_type_id=container_type_id
        ).get_or_none()

    @classmethod
    async def found_in_company_by_ids(
        cls, company_id: str, container_type_ids: list[str]
    ) -> dict[str, Self]:
        if not container_type_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, container_type_id__in=container_type_ids
        ).all()
        return {row.container_type_id: row for row in rows}

    @classmethod
    async def list_for_warehouse_by_name_asc(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Все типы контейнеров склада, ORDER BY name ASC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("name").all()

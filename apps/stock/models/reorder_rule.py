"""Правило пополнения (``stock_reorder_rules``) — min/max на полке.

Бизнес-термин min/max rule: «на этой полке товара должно быть
от ``min_qty`` до ``max_qty``». Тик ``stock_reorder_tick``
(stock_worker) считает текущий остаток поддерева локации; если он
упал ниже ``min_qty`` — создаётся черновик прихода/перемещения на
``max_qty - текущий`` через ``origin_document_type='reorder_rule'``,
``origin_document_id=rule_id``. Повторный тик не плодит дубли: открытый
move по этому же правилу блокирует новое создание, пока не проведён
или не отменён.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import QTY_DB, STOCK_DB, new_id
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockReorderRule(PlatformModel):
    """Правило «полка не должна пустеть»: min/max на локацию × товар."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_reorder_rules"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id"]),
            Index(["company_id", "product_id"]),
        ]

    rule_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    product_id: str = DbField(max_length=64)
    location_id: str = DbField(max_length=64)
    """Корень поддерева, чей остаток охраняется (bin или зона)."""
    min_qty: Decimal = DbField(db_type=QTY_DB)
    """Нижняя граница: остаток < min → триггер пополнения."""
    max_qty: Decimal = DbField(db_type=QTY_DB)
    """Целевой запас: пополняем до max_qty."""
    operation_type_id: str = DbField(max_length=64)
    """Тип операции пополнения (обычно incoming — «закупить»)."""
    route_id: str | None = DbField(default=None, max_length=64)
    """Маршрут цепочки пополнения: задан — строка создаваемого
    драфта разворачивается в плечи маршрута (например bulk-хранение →
    forward-зона вместо прямого заказа поставщику)."""
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, rule_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, rule_id=rule_id
        ).get_or_none()

    @classmethod
    async def list_for_company(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None = None,
        active_only: bool = False,
        limit: int = 500,
    ) -> list[Self]:
        q = cls.objects.filter(company_id=company_id)
        if warehouse_id is not None:
            q = q.filter(warehouse_id=warehouse_id)
        if active_only:
            q = q.filter(is_active=True)
        return await q.order_by("rule_id").limit(limit).all()

    @classmethod
    async def create_rule(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        product_id: str,
        location_id: str,
        min_qty: Decimal,
        max_qty: Decimal,
        operation_type_id: str,
        route_id: str | None = None,
    ) -> Self:
        now = utcnow()
        return await cls.objects.create(
            instance=cls(
                rule_id=new_id("ror"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                location_id=location_id,
                min_qty=min_qty,
                max_qty=max_qty,
                operation_type_id=operation_type_id,
                route_id=route_id,
                created_at=now,
                updated_at=now,
            )
        )

    @classmethod
    async def set_active(
        cls, company_id: str, rule_id: str, active: bool
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, rule_id=rule_id
        ).update(using=STOCK_DB, is_active=active, updated_at=utcnow())

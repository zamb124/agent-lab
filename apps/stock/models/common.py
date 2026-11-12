"""Общие константы, идентификаторы и полосы таблиц склада."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from core.errors.boundary import PlatformConflictError
from core.lanes import lane_id_for
from core.models import StrictBaseModel

STOCK_DB = "stock"
QTY_DB = "NUMERIC(20,6)"
MONEY_DB = "NUMERIC(24,6)"
STOCK_ZERO = Decimal("0")
STOCK_ONE = Decimal("1")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def stock_warehouse_lane(company_id: str, warehouse_id: str) -> str:
    """Полоса склада: сериализует все мутации леджера площадки."""
    return lane_id_for("stock_wh", company_id, warehouse_id)


def stock_company_lane(company_id: str) -> str:
    """Полоса компании: леджерные команды без привязки к складу (оценка, строки без перевода)."""
    return lane_id_for("stock_company", company_id, "ledger")


def stock_ledger_cursor(company_id: str) -> str:
    """Курсор ``entry_no`` журнала оценки компании в ``lane_cursors``.

    No-gap нумерация записей ``stock_value_layers``: номер выделяется
    в той же транзакции, что и слой, — при откате номер откатывается,
    пропусков нет. Та же строка под ``FOR UPDATE`` — сериализующая
    точка журнала компании: смена ``valuation_method`` ждёт
    незакоммиченных писателей слоёв и видит только зафиксированные.
    """
    return lane_id_for("stock_ledger", company_id, "entry_no")


def stock_command_lane(company_id: str, warehouse_id: str | None) -> str:
    """Полоса по складу, а при отсутствии склада — компании."""
    if warehouse_id:
        return stock_warehouse_lane(company_id, warehouse_id)
    return stock_company_lane(company_id)


class StockMoveSpec(StrictBaseModel):
    """Строка движения в create-transfer — вход тела ``create_in_lane``.

    `product_qty` — в `uom_id` документа; при создании move конвертируется
    в базовую ЕИ товара (`product_qty`), doc-количество — `product_uom_qty`.
    """

    product_id: str
    product_qty: Decimal = Field(gt=0)
    uom_id: str
    unit_price: Decimal | None = Field(default=None, ge=0)
    location_id: str | None = None
    location_dest_id: str | None = None
    route_id: str | None = None
    """Маршрут цепочки: спека разворачивается в плечи по шагам маршрута."""
    priority: int | None = None
    date_deadline: datetime | None = None


def require_stock(condition: bool, message: str, *, error_code: str) -> None:
    if not condition:
        raise PlatformConflictError(message, error_code=error_code)

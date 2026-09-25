"""
Чистая математика оценки запасов (без IO и без зависимости от моделей).

Классификация хозоперации по паре `usage` локаций и выбор `unit_cost` по методу
оценки. Весь SQL — в classmethod'ах `StockValueLayer`/`StockQuant` (domain.py);
здесь — детерминированные функции над примитивами и generic-записями.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal

from apps.stock.models.enums import (
    StockLocationUsage,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)

_Q = Decimal("0.000001")


def quantize(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


def classify_entry(
    src_usage: StockLocationUsage,
    dst_usage: StockLocationUsage,
    *,
    is_return: bool,
) -> list[ValueEntryKind]:
    """Матрица записи по паре usage: 1 слой, либо пара out/in для internal→internal."""
    src_internal = src_usage == StockLocationUsage.INTERNAL
    dst_internal = dst_usage == StockLocationUsage.INTERNAL
    if src_internal and dst_internal:
        return [ValueEntryKind.INTERNAL_OUT, ValueEntryKind.INTERNAL_IN]
    if dst_internal:
        if src_usage == StockLocationUsage.INVENTORY:
            return [ValueEntryKind.INVENTORY_GAIN]
        if is_return or src_usage == StockLocationUsage.CUSTOMER:
            return [ValueEntryKind.RETURN]
        return [ValueEntryKind.INBOUND]
    if src_internal:
        if dst_usage == StockLocationUsage.INVENTORY:
            return [ValueEntryKind.INVENTORY_LOSS]
        # Исходящий возврат поставщику — тот же расход по стоимости origin.
        return [ValueEntryKind.OUTBOUND]
    return []


def inbound_unit_cost(
    unit_price: Decimal | None,
    method: ValuationMethod,
    standard_price: Decimal,
) -> tuple[Decimal, ValuationPriceSource]:
    """Стоимость входящей единицы: цена документа, иначе карточка/среднее."""
    if unit_price is not None:
        return unit_price, ValuationPriceSource.DOCUMENT
    if method == ValuationMethod.AVERAGE:
        return standard_price, ValuationPriceSource.AVERAGE
    return standard_price, ValuationPriceSource.STANDARD


def fifo_allocate[T](
    layers: Sequence[T],
    quantity: Decimal,
    *,
    remaining_of: Callable[[T], Decimal],
) -> list[tuple[T, Decimal]]:
    """Распределение outgoing-количества по открытым слоям (уже отсортированы по entry_no)."""
    plan: list[tuple[T, Decimal]] = []
    rest = quantity
    for layer in layers:
        if rest <= Decimal("0"):
            break
        take = min(remaining_of(layer), rest)
        if take > Decimal("0"):
            plan.append((layer, take))
            rest -= take
    return plan


def fifo_cost_of[T](
    layers: Sequence[T],
    quantity: Decimal,
    *,
    remaining_of: Callable[[T], Decimal],
    cost_of: Callable[[T], Decimal],
) -> tuple[Decimal, Decimal]:
    """`(value, unit_cost)` по плану fifo_allocate; остаток — по цене последнего слоя."""
    plan = fifo_allocate(layers, quantity, remaining_of=remaining_of)
    covered = sum((take for _, take in plan), Decimal("0"))
    value = sum((quantize(cost_of(layer) * take) for layer, take in plan), Decimal("0"))
    uncovered = quantity - covered
    if uncovered > Decimal("0") and plan:
        last_cost = cost_of(plan[-1][0])
        value += quantize(last_cost * uncovered)
    unit = value / quantity if quantity > Decimal("0") else Decimal("0")
    return value, quantize(unit)

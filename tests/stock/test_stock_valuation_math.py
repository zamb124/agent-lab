"""Unit-тесты чистой математики оценки: `apps/stock/models/valuation.py`.

Без БД и стека — детерминированные функции над примитивами.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.stock.models.enums import (
    StockLocationUsage,
    StockPartnerRole,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)
from apps.stock.models.valuation import (
    classify_entry,
    fifo_allocate,
    fifo_cost_of,
    inbound_unit_cost,
    quantize,
)

BIN = StockLocationUsage.BIN
CONTAINER = StockLocationUsage.CONTAINER
PARTNER = StockLocationUsage.PARTNER
TRANSIT = StockLocationUsage.TRANSIT
ADJUSTMENT = StockLocationUsage.ADJUSTMENT
VENDOR = StockPartnerRole.VENDOR
CUSTOMER_ROLE = StockPartnerRole.CUSTOMER


class TestQuantize:
    def test_rounds_half_up_to_six_decimals(self) -> None:
        assert quantize(Decimal("1.2345675")) == Decimal("1.234568")
        assert quantize(Decimal("0.0000004")) == Decimal("0")

    def test_keeps_exact_values(self) -> None:
        assert quantize(Decimal("10")) == Decimal("10")
        assert quantize(Decimal("-3.5")) == Decimal("-3.5")


class TestClassifyEntry:
    def test_vendor_to_bin_is_inbound(self) -> None:
        assert classify_entry(
            PARTNER, BIN, is_return=False, src_partner_role=VENDOR
        ) == [ValueEntryKind.INBOUND]

    def test_bin_to_customer_is_outbound(self) -> None:
        assert classify_entry(
            BIN, PARTNER, is_return=False
        ) == [ValueEntryKind.OUTBOUND]

    def test_valued_to_valued_writes_nothing(self) -> None:
        assert classify_entry(BIN, CONTAINER, is_return=False) == []
        assert classify_entry(BIN, TRANSIT, is_return=False) == []
        assert classify_entry(BIN, BIN, is_return=False) == []

    def test_inventory_gain_and_loss(self) -> None:
        assert classify_entry(ADJUSTMENT, BIN, is_return=False) == [
            ValueEntryKind.INVENTORY_GAIN
        ]
        assert classify_entry(BIN, ADJUSTMENT, is_return=False) == [
            ValueEntryKind.INVENTORY_LOSS
        ]

    def test_returns(self) -> None:
        # Возврат от клиента — по partner_role, без флага.
        assert classify_entry(
            PARTNER, BIN, is_return=False, src_partner_role=CUSTOMER_ROLE
        ) == [ValueEntryKind.RETURN]
        # Возврат от поставщика (брак принятого) — по флагу.
        assert classify_entry(
            PARTNER, BIN, is_return=True, src_partner_role=VENDOR
        ) == [ValueEntryKind.RETURN]
        # Возврат поставщику — исходящий (отрицательный) по стоимости origin.
        assert classify_entry(
            BIN, PARTNER, is_return=True, src_partner_role=VENDOR
        ) == [ValueEntryKind.OUTBOUND]

    def test_virtual_to_virtual_writes_nothing(self) -> None:
        assert classify_entry(PARTNER, PARTNER, is_return=False) == []
        assert classify_entry(PARTNER, ADJUSTMENT, is_return=False) == []

    def test_consigned_stock_writes_nothing(self) -> None:
        assert (
            classify_entry(
                BIN, PARTNER, is_return=False, owner_entity_id="ent1"
            )
            == []
        )
        assert (
            classify_entry(
                PARTNER, BIN, is_return=False, owner_entity_id="ent1"
            )
            == []
        )


class TestInboundUnitCost:
    def test_document_price_wins(self) -> None:
        cost, source = inbound_unit_cost(
            Decimal("42"), ValuationMethod.FIFO, Decimal("10")
        )
        assert cost == Decimal("42")
        assert source == ValuationPriceSource.DOCUMENT

    def test_average_falls_back_to_card_price(self) -> None:
        cost, source = inbound_unit_cost(
            None, ValuationMethod.AVERAGE, Decimal("7.5")
        )
        assert cost == Decimal("7.5")
        assert source == ValuationPriceSource.AVERAGE

    def test_standard_and_fifo_use_card_price(self) -> None:
        for method in (ValuationMethod.STANDARD, ValuationMethod.FIFO):
            cost, source = inbound_unit_cost(None, method, Decimal("3"))
            assert cost == Decimal("3")
            assert source == ValuationPriceSource.STANDARD


@dataclass
class _Layer:
    remaining: Decimal
    cost: Decimal


def _remaining(layer: _Layer) -> Decimal:
    return layer.remaining


def _cost(layer: _Layer) -> Decimal:
    return layer.cost


class TestFifoAllocate:
    def test_allocates_oldest_first(self) -> None:
        layers = [
            _Layer(Decimal("2"), Decimal("10")),
            _Layer(Decimal("5"), Decimal("20")),
        ]
        plan = fifo_allocate(layers, Decimal("4"), remaining_of=_remaining)
        assert [(take, layer.cost) for layer, take in plan] == [
            (Decimal("2"), Decimal("10")),
            (Decimal("2"), Decimal("20")),
        ]

    def test_empty_layers_gives_empty_plan(self) -> None:
        assert fifo_allocate([], Decimal("1"), remaining_of=_remaining) == []


class TestFifoCostOf:
    def test_full_coverage(self) -> None:
        layers = [
            _Layer(Decimal("2"), Decimal("10")),
            _Layer(Decimal("5"), Decimal("20")),
        ]
        value, unit = fifo_cost_of(
            layers, Decimal("4"), remaining_of=_remaining, cost_of=_cost
        )
        assert value == Decimal("60")
        assert unit == Decimal("15")

    def test_uncovered_rest_priced_by_last_layer(self) -> None:
        layers = [_Layer(Decimal("2"), Decimal("10"))]
        value, unit = fifo_cost_of(
            layers, Decimal("3"), remaining_of=_remaining, cost_of=_cost
        )
        assert value == Decimal("30")
        assert unit == Decimal("10")

    def test_zero_quantity(self) -> None:
        value, unit = fifo_cost_of(
            [_Layer(Decimal("1"), Decimal("9"))],
            Decimal("0"),
            remaining_of=_remaining,
            cost_of=_cost,
        )
        assert value == Decimal("0")
        assert unit == Decimal("0")

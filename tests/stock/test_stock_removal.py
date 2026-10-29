"""Чистые стратегии отбора (без БД): fifo/fefo/lifo/closest/least_containers.

`order_candidates_by_strategy_asc`/`full_container_cover` работают на frozen-двойниках
StockQuant — проверяем только очередь обхода кандидатов, не данные.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.stock.models.enums import StockLocationUsage, StockRemovalStrategy
from apps.stock.models.removal import (
    RemovalBin,
    container_exact_cover,
    order_candidates_by_strategy_asc,
)


@dataclass(frozen=True)
class _Quant:
    quant_id: str
    location_id: str
    product_id: str = "p-1"
    owner_entity_id: str | None = None
    quantity: Decimal = Decimal("10")
    reserved_quantity: Decimal = Decimal("0")
    lot_id: str | None = None
    in_date: datetime | None = None
    removal_at: datetime | None = None

    @property
    def available_quantity(self) -> Decimal:
        return self.quantity - self.reserved_quantity


def _bin(
    location_id: str,
    *,
    usage: StockLocationUsage = StockLocationUsage.BIN,
    pick_sequence: int = 0,
) -> RemovalBin:
    return RemovalBin(usage=usage, pick_sequence=pick_sequence)


def _ids(ordered: list[_Quant]) -> list[str]:
    return [q.quant_id for q in ordered]


_D1 = datetime(2026, 1, 1)
_D2 = datetime(2026, 2, 1)
_D3 = datetime(2026, 3, 1)


class TestFifo:
    def test_oldest_first(self) -> None:
        quants = [
            _Quant("q-new", "loc-a", in_date=_D3),
            _Quant("q-old", "loc-a", in_date=_D1),
            _Quant("q-mid", "loc-a", in_date=_D2),
        ]
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.FIFO,
            needed=Decimal("5"),
            locations={"loc-a": _bin("loc-a")},
        )
        assert _ids(ordered) == ["q-old", "q-mid", "q-new"]

    def test_tie_breaks_by_quant_id(self) -> None:
        quants = [
            _Quant("q-b", "loc-a", in_date=_D1),
            _Quant("q-a", "loc-a", in_date=_D1),
        ]
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.FIFO,
            needed=Decimal("5"),
            locations={},
        )
        assert _ids(ordered) == ["q-a", "q-b"]


class TestLifo:
    def test_newest_first(self) -> None:
        quants = [
            _Quant("q-old", "loc-a", in_date=_D1),
            _Quant("q-new", "loc-a", in_date=_D3),
            _Quant("q-mid", "loc-a", in_date=_D2),
        ]
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.LIFO,
            needed=Decimal("5"),
            locations={},
        )
        assert _ids(ordered) == ["q-new", "q-mid", "q-old"]


class TestFefo:
    def test_earliest_removal_first(self) -> None:
        quants = [
            _Quant("q-late", "loc-a", removal_at=_D3),
            _Quant("q-soon", "loc-a", removal_at=_D1),
        ]
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.FEFO,
            needed=Decimal("5"),
            locations={},
        )
        assert _ids(ordered) == ["q-soon", "q-late"]

    def test_no_removal_date_goes_last(self) -> None:
        quants = [
            _Quant("q-none", "loc-a", in_date=_D1),
            _Quant("q-exp", "loc-a", in_date=_D3, removal_at=_D2),
        ]
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.FEFO,
            needed=Decimal("5"),
            locations={},
        )
        assert _ids(ordered) == ["q-exp", "q-none"]


class TestClosest:
    def test_lowest_pick_sequence_first(self) -> None:
        quants = [
            _Quant("q-far", "loc-far", in_date=_D1),
            _Quant("q-near", "loc-near", in_date=_D3),
        ]
        bins = {
            "loc-near": _bin("loc-near", pick_sequence=1),
            "loc-far": _bin("loc-far", pick_sequence=99),
        }
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.CLOSEST,
            needed=Decimal("5"),
            locations=bins,
        )
        # Свежая партия из ближней ячейки идёт раньше старой из дальней.
        assert _ids(ordered) == ["q-near", "q-far"]

    def test_same_sequence_falls_back_to_fifo(self) -> None:
        quants = [
            _Quant("q-new", "loc-a", in_date=_D3),
            _Quant("q-old", "loc-a", in_date=_D1),
        ]
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.CLOSEST,
            needed=Decimal("5"),
            locations={"loc-a": _bin("loc-a", pick_sequence=5)},
        )
        assert _ids(ordered) == ["q-old", "q-new"]


class TestLeastContainers:
    def _setup(self) -> tuple[list[_Quant], dict[str, RemovalBin]]:
        quants = [
            _Quant("q-pallet", "loc-pal", quantity=Decimal("40"), in_date=_D2),
            _Quant("q-bin", "loc-bin", quantity=Decimal("50"), in_date=_D1),
        ]
        bins = {
            "loc-pal": _bin("loc-pal", usage=StockLocationUsage.CONTAINER),
            "loc-bin": _bin("loc-bin"),
        }
        return quants, bins

    def test_covering_container_goes_first(self) -> None:
        quants, bins = self._setup()
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.LEAST_CONTAINERS,
            needed=Decimal("30"),
            locations=bins,
        )
        # Ячейка старше (in_date раньше), но паллета покрывает заказ целиком.
        assert _ids(ordered) == ["q-pallet", "q-bin"]

    def test_smallest_sufficient_container_first(self) -> None:
        quants = [
            _Quant("q-big", "loc-big", quantity=Decimal("1000"), in_date=_D1),
            _Quant("q-fit", "loc-fit", quantity=Decimal("24"), in_date=_D3),
        ]
        bins = {
            "loc-big": _bin("loc-big", usage=StockLocationUsage.CONTAINER),
            "loc-fit": _bin("loc-fit", usage=StockLocationUsage.CONTAINER),
        }
        ordered = order_candidates_by_strategy_asc(
            quants,
            strategy=StockRemovalStrategy.LEAST_CONTAINERS,
            needed=Decimal("20"),
            locations=bins,
        )
        assert _ids(ordered) == ["q-fit", "q-big"]

    def test_exact_cover_returns_contents_qty(self) -> None:
        inside = [
            _Quant("q-1", "loc-pal", quantity=Decimal("20")),
            _Quant("q-2", "loc-pal", quantity=Decimal("20")),
        ]
        total = container_exact_cover(
            inside, product_id="p-1", owner_entity_id=None, needed=Decimal("30")
        )
        assert total == Decimal("40")

    def test_mixed_product_container_not_covering(self) -> None:
        inside = [
            _Quant("q-1", "loc-pal", quantity=Decimal("40")),
            _Quant("q-x", "loc-pal", product_id="p-9", quantity=Decimal("5")),
        ]
        assert (
            container_exact_cover(
                inside,
                product_id="p-1",
                owner_entity_id=None,
                needed=Decimal("30"),
            )
            is None
        )

    def test_reserved_inside_not_covering(self) -> None:
        inside = [
            _Quant(
                "q-pal",
                "loc-pal",
                quantity=Decimal("40"),
                reserved_quantity=Decimal("15"),
            )
        ]
        assert (
            container_exact_cover(
                inside,
                product_id="p-1",
                owner_entity_id=None,
                needed=Decimal("30"),
            )
            is None
        )

    def test_short_container_not_covering(self) -> None:
        inside = [_Quant("q-pal", "loc-pal", quantity=Decimal("20"))]
        assert (
            container_exact_cover(
                inside,
                product_id="p-1",
                owner_entity_id=None,
                needed=Decimal("30"),
            )
            is None
        )

    def test_owner_mismatch_not_covering(self) -> None:
        inside = [
            _Quant("q-pal", "loc-pal", quantity=Decimal("40"), owner_entity_id="o-1")
        ]
        assert (
            container_exact_cover(
                inside,
                product_id="p-1",
                owner_entity_id=None,
                needed=Decimal("30"),
            )
            is None
        )

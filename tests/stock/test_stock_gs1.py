"""GS1-парсер и чистые правила размещения/ресурсов (без БД).

`parse_gs1` не бросает на мусоре — обрыв разбора оставляет извлечённое.
`check_placement`/`resource_allows` — чистые функции над Protocol-двойниками.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from apps.stock.models.enums import StockContainerPolicy, StockProductMixing
from apps.stock.models.gs1 import parse_gs1, strip_symbology_prefix
from apps.stock.models.storage_rules import (
    BinContent,
    PlacementItem,
    check_placement,
    resource_allows,
)

_GS = "\x1d"


class TestGs1Parse:
    def test_plain_code_is_not_gs1(self) -> None:
        parsed = parse_gs1("4815162342")
        assert not parsed.is_gs1
        assert parsed.ais == {}

    def test_gtin_only(self) -> None:
        parsed = parse_gs1("0104607025392165")
        assert parsed.is_gs1
        assert parsed.gtin == "04607025392165"

    def test_symbology_prefix_stripped(self) -> None:
        assert strip_symbology_prefix("]C10104607025392165") == "0104607025392165"
        assert strip_symbology_prefix("]d20104607025392165") == "0104607025392165"
        assert strip_symbology_prefix("4607025392165") == "4607025392165"
        parsed = parse_gs1("]C10104607025392165")
        assert parsed.gtin == "04607025392165"

    def test_sscc(self) -> None:
        parsed = parse_gs1("00012345678901234567")
        assert parsed.sscc == "012345678901234567"

    def test_gtin_lot_expiry_serial(self) -> None:
        code = f"0104607025392165{_GS}10LOT-42{_GS}17260315{_GS}21SN001"
        parsed = parse_gs1(code)
        assert parsed.gtin == "04607025392165"
        assert parsed.lot_name == "LOT-42"
        assert parsed.expiration_date == date(2026, 3, 15)
        assert parsed.serial == "SN001"

    def test_weight_ai(self) -> None:
        # 3103 — 3 знака после запятой: 001500 → 1.500 кг.
        parsed = parse_gs1("01046070253921653103001500")
        assert parsed.weight_kg == Decimal("1.5")

    def test_quantity_variable(self) -> None:
        parsed = parse_gs1(f"0104607025392165{_GS}3012")
        assert parsed.quantity == Decimal("12")

    def test_date_day_zero_is_month_end(self) -> None:
        parsed = parse_gs1("010460702539216517260200")
        assert parsed.expiration_date == date(2026, 2, 28)

    def test_garbage_tail_stops_parse(self) -> None:
        parsed = parse_gs1("0104607025392165ZZZ")
        assert parsed.gtin == "04607025392165"

    def test_variable_field_runs_to_end(self) -> None:
        parsed = parse_gs1("10LOT-ONLY")
        assert parsed.lot_name == "LOT-ONLY"


@dataclass(frozen=True)
class _StorageType:
    container_policy: StockContainerPolicy = StockContainerPolicy.ANY
    allowed_container_type_ids: list[str] = field(default_factory=list)
    max_containers: int | None = None
    product_mixing: StockProductMixing = StockProductMixing.MIXED
    allow_mixed_lots: bool = True
    max_weight: Decimal | None = None
    max_volume: Decimal | None = None


@dataclass(frozen=True)
class _ResourceType:
    allowed_container_type_ids: list[str] = field(default_factory=list)
    handles_loose: bool = True
    max_level: int | None = None
    max_load_weight: Decimal | None = None
    storage_type_ids: list[str] = field(default_factory=list)


_BASE_ITEM = PlacementItem(
    product_ids=frozenset({"p1"}),
    lot_ids=frozenset(),
    container_type_id=None,
    total_weight=None,
    total_volume=None,
)

_BASE_BIN = BinContent(
    product_ids=frozenset(),
    lot_ids=frozenset(),
    container_type_ids=frozenset(),
    container_count=0,
    has_loose=False,
    total_weight=Decimal("0"),
    total_volume=Decimal("0"),
)


def _item(**kwargs: object) -> PlacementItem:
    return replace(_BASE_ITEM, **kwargs)


def _bin(**kwargs: object) -> BinContent:
    return replace(_BASE_BIN, **kwargs)


class TestCheckPlacement:
    def test_empty_bin_any_policy_ok(self) -> None:
        assert check_placement(
            storage_type=_StorageType(), placing=_item(), existing=_bin()
        ) is None

    def test_loose_only_rejects_container(self) -> None:
        assert (
            check_placement(
                storage_type=_StorageType(
                    container_policy=StockContainerPolicy.LOOSE_ONLY
                ),
                placing=_item(container_type_id="ct1"),
                existing=_bin(),
            )
            == "storage_loose_only"
        )

    def test_container_only_rejects_loose(self) -> None:
        assert (
            check_placement(
                storage_type=_StorageType(
                    container_policy=StockContainerPolicy.CONTAINER_ONLY
                ),
                placing=_item(),
                existing=_bin(),
            )
            == "storage_container_required"
        )

    def test_allowed_container_types(self) -> None:
        st = _StorageType(allowed_container_type_ids=["ct-ok"])
        assert (
            check_placement(
                storage_type=st,
                placing=_item(container_type_id="ct-bad"),
                existing=_bin(),
            )
            == "storage_container_type_denied"
        )
        assert (
            check_placement(
                storage_type=st,
                placing=_item(container_type_id="ct-ok"),
                existing=_bin(),
            )
            is None
        )

    def test_max_containers(self) -> None:
        st = _StorageType(max_containers=1)
        assert (
            check_placement(
                storage_type=st,
                placing=_item(container_type_id="ct1"),
                existing=_bin(container_count=1),
            )
            == "storage_max_containers"
        )
        # Россыпь не считается контейнером.
        assert (
            check_placement(
                storage_type=st, placing=_item(), existing=_bin(container_count=1)
            )
            is None
        )

    def test_empty_only(self) -> None:
        st = _StorageType(product_mixing=StockProductMixing.EMPTY_ONLY)
        assert (
            check_placement(
                storage_type=st, placing=_item(), existing=_bin(product_ids={"p9"})
            )
            == "storage_not_empty"
        )

    def test_same_product(self) -> None:
        st = _StorageType(product_mixing=StockProductMixing.SAME_PRODUCT)
        assert (
            check_placement(
                storage_type=st,
                placing=_item(product_ids=frozenset({"p2"})),
                existing=_bin(product_ids={"p1"}),
            )
            == "storage_product_mixed"
        )
        assert (
            check_placement(
                storage_type=st,
                placing=_item(product_ids=frozenset({"p1"})),
                existing=_bin(product_ids={"p1"}),
            )
            is None
        )

    def test_lot_mixing(self) -> None:
        st = _StorageType(allow_mixed_lots=False)
        assert (
            check_placement(
                storage_type=st,
                placing=_item(lot_ids=frozenset({"l2"})),
                existing=_bin(lot_ids={"l1"}),
            )
            == "storage_lot_mixed"
        )

    def test_capacity(self) -> None:
        st = _StorageType(max_weight=Decimal("100"), max_volume=Decimal("10"))
        assert (
            check_placement(
                storage_type=st,
                placing=_item(total_weight=Decimal("60")),
                existing=_bin(total_weight=Decimal("50")),
            )
            == "storage_capacity_exceeded"
        )
        assert (
            check_placement(
                storage_type=st,
                placing=_item(total_weight=Decimal("50")),
                existing=_bin(total_weight=Decimal("50")),
            )
            is None
        )
        assert (
            check_placement(
                storage_type=st,
                placing=_item(total_volume=Decimal("11")),
                existing=_bin(),
            )
            == "storage_capacity_exceeded"
        )


class TestResourceAllows:
    def test_plain_resource_allows_everything(self) -> None:
        assert (
            resource_allows(
                resource_type=_ResourceType(),
                container_type_id=None,
                loose=True,
                src_level=1,
                dst_level=2,
                src_storage_type_id=None,
                dst_storage_type_id=None,
                load_weight=None,
            )
            is None
        )

    def test_level_cap(self) -> None:
        rt = _ResourceType(max_level=2)
        assert (
            resource_allows(
                resource_type=rt,
                container_type_id=None,
                loose=True,
                src_level=1,
                dst_level=5,
                src_storage_type_id=None,
                dst_storage_type_id=None,
                load_weight=None,
            )
            == "resource_level_exceeded"
        )

    def test_loose_denied(self) -> None:
        rt = _ResourceType(handles_loose=False)
        assert (
            resource_allows(
                resource_type=rt,
                container_type_id="ct1",
                loose=True,
                src_level=None,
                dst_level=None,
                src_storage_type_id=None,
                dst_storage_type_id=None,
                load_weight=None,
            )
            == "resource_loose_denied"
        )

    def test_container_whitelist(self) -> None:
        rt = _ResourceType(allowed_container_type_ids=["ct-ok"])
        assert (
            resource_allows(
                resource_type=rt,
                container_type_id="ct-bad",
                loose=False,
                src_level=None,
                dst_level=None,
                src_storage_type_id=None,
                dst_storage_type_id=None,
                load_weight=None,
            )
            == "resource_container_denied"
        )

    def test_overweight(self) -> None:
        rt = _ResourceType(max_load_weight=Decimal("500"))
        assert (
            resource_allows(
                resource_type=rt,
                container_type_id=None,
                loose=True,
                src_level=None,
                dst_level=None,
                src_storage_type_id=None,
                dst_storage_type_id=None,
                load_weight=Decimal("600"),
            )
            == "resource_overweight"
        )

    def test_zone_restriction(self) -> None:
        rt = _ResourceType(storage_type_ids=["st-a"])
        assert (
            resource_allows(
                resource_type=rt,
                container_type_id=None,
                loose=True,
                src_level=None,
                dst_level=None,
                src_storage_type_id="st-a",
                dst_storage_type_id="st-b",
                load_weight=None,
            )
            == "resource_zone_denied"
        )
        assert (
            resource_allows(
                resource_type=rt,
                container_type_id=None,
                loose=True,
                src_level=None,
                dst_level=None,
                src_storage_type_id="st-a",
                dst_storage_type_id="st-a",
                load_weight=None,
            )
            is None
        )

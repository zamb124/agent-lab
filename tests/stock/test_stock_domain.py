"""Интеграционные доменные тесты stock через `stock_di` (продовый путь).

Реальный Postgres `platform_stock`, настоящий OpenFGA (warehouse defaults
пишут tuples). Изоляция — уникальный `company_id` на тест.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

import pytest

from apps.stock.di import StockDi
from apps.stock.models import (
    StockLayoutPreset,
    StockLocationUsage,
    StockMoveState,
    StockOperationCode,
    StockOperationType,
    StockPartnerRole,
    StockProduct,
    StockQuant,
    StockRemovalStrategy,
    StockTracking,
    StockTransferState,
    StockValueLayer,
    StockWarehouse,
    UnitOfMeasure,
    ValuationMethod,
    ValueEntryKind,
)
from apps.stock.models.api import StockMoveSpec
from apps.stock.services.company_init_service import virtual_location_id
from apps.stock.services.warehouse_service import WarehouseService
from core.errors.boundary import PlatformConflictError

_COMPANY = "system"


@dataclass
class StockEnv:
    """Склад + продукт + типы операций свежей компании."""

    di: StockDi
    company_id: str
    warehouse: StockWarehouse
    op_types: dict[StockOperationCode, StockOperationType]
    product: StockProduct
    uom_id: str


async def _make_env(
    di: StockDi, company_id: str, unique: str, valuation: ValuationMethod
) -> StockEnv:
    await di.company_init_service.init_company_stock(company_id=company_id)
    warehouse = await di.warehouse_service.create_warehouse(
        company_id=company_id,
        code=f"WH{unique[:8]}",
        name=f"Warehouse {unique}",
        owner_user_id="test_user",

        layout_preset=StockLayoutPreset.SIMPLE,

        removal_strategy=StockRemovalStrategy.FIFO,
    )
    uom = await UnitOfMeasure.objects.filter(
        company_id=company_id, name="Units"
    ).first()
    assert uom is not None
    product = await di.catalog_service.create_product(
        company_id=company_id,
        name=f"Widget {unique}",
        sku=f"SKU-{unique}",
        uom_id=uom.uom_id,
        valuation_method=valuation,
        standard_price=Decimal("0"),
        tracking=StockTracking.NONE,
        is_storable=True,
        category="general",
        barcode=None,
    )
    op_types = {
        op.code: op
        for op in await di.warehouse_service.list_operation_types(
            company_id=company_id, warehouse_id=warehouse.warehouse_id
        )
    }
    return StockEnv(
        di=di,
        company_id=company_id,
        warehouse=warehouse,
        op_types=op_types,
        product=product,
        uom_id=uom.uom_id,
    )


async def _receipt(
    env: StockEnv,
    qty: Decimal,
    unit_price: Decimal | None,
) -> str:
    """INCOMING supplier→stock через полный цикл; возвращает transfer_id."""
    op = env.op_types[StockOperationCode.INCOMING]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=op.operation_type_id,
        partner_entity_id=None,
        owner_entity_id=None,
        scheduled_at=None,
        origin_document_type=None,
        origin_document_id=None,
        barcode=None,
        moves=[
            StockMoveSpec(
                product_id=env.product.product_id,
                product_qty=qty,
                uom_id=env.uom_id,
                unit_price=unit_price,
            )
        ],
    )
    _ = await env.di.move_engine.confirm_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    _ = await env.di.move_engine.assign_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    _ = await env.di.move_engine.validate_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    return transfer.transfer_id


async def _delivery(env: StockEnv, qty: Decimal) -> str:
    op = env.op_types[StockOperationCode.OUTGOING]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=op.operation_type_id,
        partner_entity_id=None,
        owner_entity_id=None,
        scheduled_at=None,
        origin_document_type=None,
        origin_document_id=None,
        barcode=None,
        moves=[
            StockMoveSpec(
                product_id=env.product.product_id,
                product_qty=qty,
                uom_id=env.uom_id,
            )
        ],
    )
    _ = await env.di.move_engine.confirm_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    _ = await env.di.move_engine.assign_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    _ = await env.di.move_engine.validate_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    return transfer.transfer_id


async def _stock_quant(env: StockEnv) -> StockQuant | None:
    return await StockQuant.by_key(
        company_id=env.company_id,
        product_id=env.product.product_id,
        location_id=env.warehouse.stock_location_id,
        lot_id=None,
        owner_entity_id=None,
    )


async def _layers(env: StockEnv) -> list[StockValueLayer]:
    return await StockValueLayer.objects.filter(
        company_id=env.company_id, product_id=env.product.product_id
    ).order_by("entry_no").all()


class TestCompanyInit:
    async def test_init_creates_virtual_locations_and_uoms(
        self, stock_di, unique_id: str
    ) -> None:
        company = f"co-{unique_id}"
        created = await stock_di.company_init_service.init_company_stock(
            company_id=company
        )
        usages = {loc.usage for loc in created}
        assert StockLocationUsage.PARTNER in usages
        assert StockLocationUsage.ADJUSTMENT in usages
        assert StockLocationUsage.TRANSIT in usages
        roles = {loc.partner_role for loc in created}
        assert StockPartnerRole.VENDOR in roles
        assert StockPartnerRole.CUSTOMER in roles
        uoms = await UnitOfMeasure.objects.filter(company_id=company).all()
        assert {u.name for u in uoms} >= {"Units", "kg", "g", "m", "l"}

    async def test_init_is_idempotent(
        self, stock_di, unique_id: str
    ) -> None:
        company = f"co-{unique_id}"
        first = await stock_di.company_init_service.init_company_stock(
            company_id=company
        )
        second = await stock_di.company_init_service.init_company_stock(
            company_id=company
        )
        assert {loc.location_id for loc in first} == {
            loc.location_id for loc in second
        }


class TestWarehouseBootstrap:
    async def test_warehouse_creates_locations_and_op_types(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO)
        assert env.warehouse.stock_location_id != env.warehouse.view_location_id
        assert set(env.op_types) == {
            StockOperationCode.INCOMING,
            StockOperationCode.OUTGOING,
            StockOperationCode.INTERNAL,
        }
        incoming = env.op_types[StockOperationCode.INCOMING]
        assert incoming.default_source_location_id == virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER, StockPartnerRole.VENDOR
        )
        assert incoming.default_dest_location_id == env.warehouse.stock_location_id

    async def test_duplicate_warehouse_code_conflicts(
        self, stock_di, unique_id: str
    ) -> None:
        company = f"co-{unique_id}"
        await _make_env(stock_di, company, unique_id, ValuationMethod.FIFO)
        service: WarehouseService = stock_di.warehouse_service
        with pytest.raises(PlatformConflictError, match="Warehouse code already exists"):
            _ = await service.create_warehouse(
                company_id=company,
                code=f"WH{unique_id[:8]}",
                name="Dup",
                owner_user_id="test_user",

                layout_preset=StockLayoutPreset.SIMPLE,

                removal_strategy=StockRemovalStrategy.FIFO,
            )


class TestIncomingCycle:
    async def test_receipt_moves_stock_and_writes_inbound_layer(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("10"), Decimal("25"))
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("10")
        assert quant.reserved_quantity == Decimal("0")
        layers = await _layers(env)
        assert len(layers) == 1
        layer = layers[0]
        assert layer.entry_kind == ValueEntryKind.INBOUND
        assert layer.quantity == Decimal("10")
        assert layer.unit_cost == Decimal("25")
        assert layer.remaining_quantity == Decimal("10")
        assert layer.qty_after == Decimal("10")

    async def test_ledger_entry_no_has_no_gaps(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("1"), Decimal("1"))
        _ = await _receipt(env, Decimal("2"), Decimal("1"))
        _ = await _delivery(env, Decimal("1"))
        nos = [layer.entry_no for layer in await _layers(env)]
        assert nos == list(range(1, len(nos) + 1))

    async def test_ledger_concurrent_receipts_no_gaps(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        await asyncio.gather(
            *[_receipt(env, Decimal("1"), Decimal("5")) for _ in range(6)]
        )
        nos = [layer.entry_no for layer in await _layers(env)]
        assert nos == list(range(1, len(nos) + 1))
        last = await StockValueLayer.last_for_product(
            env.company_id, env.product.product_id
        )
        assert last is not None
        assert last.qty_after == Decimal("6")
        assert last.value_after == Decimal("30")


class TestFifoValuation:
    async def test_fifo_consumes_oldest_layers_first(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("10"), Decimal("10"))
        _ = await _receipt(env, Decimal("10"), Decimal("20"))
        _ = await _delivery(env, Decimal("15"))
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("5")
        layers = await _layers(env)
        inbound = [
            layer for layer in layers if layer.entry_kind == ValueEntryKind.INBOUND
        ]
        outbound = [
            layer for layer in layers if layer.entry_kind == ValueEntryKind.OUTBOUND
        ]
        assert len(inbound) == 2
        assert len(outbound) == 1
        # 10 × 10 + 5 × 20 = 200 расход; единица 200/15.
        assert outbound[0].value == Decimal("-200")
        first = inbound[0]
        assert first.remaining_quantity == Decimal("0")
        assert inbound[1].remaining_quantity == Decimal("5")


class TestAverageValuation:
    async def test_average_cost_recalculated_on_receipt(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.AVERAGE
        )
        _ = await _receipt(env, Decimal("10"), Decimal("10"))
        _ = await _receipt(env, Decimal("10"), Decimal("30"))
        value = await env.di.valuation_service.product_value(
            company_id=env.company_id,
            product_id=env.product.product_id,
            warehouse_id=env.warehouse.warehouse_id,
        )
        # (10×10 + 10×30) / 20 = 20
        assert value.quantity == Decimal("20")
        assert value.avg_cost == Decimal("20")
        assert value.value == Decimal("400")


class TestPartialBackorder:
    async def test_partial_done_creates_backorder(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        op = env.op_types[StockOperationCode.INCOMING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("10"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("5"),
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _, moves, lines = await env.di.warehouse_service.get_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        assert len(lines) == 1
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=lines[0].move_line_id,
            done_quantity=Decimal("4"),
            picked=None,
            lot_id=None,
            location_dest_id=None,
        )
        done = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        assert done.state == StockTransferState.DONE
        assert moves[0].state in {
            StockMoveState.ASSIGNED,
            StockMoveState.CONFIRMED,
            StockMoveState.DONE,
        }
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("4")
        # Бэкордер на остаток 6.
        transfers = await env.di.warehouse_service.list_transfers(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            state=None,
            limit=10,
            offset=0,
        )
        backorders = [t for t in transfers.items if t.backorder_of_id is not None]
        assert len(backorders) == 1
        _, back_moves, _ = await env.di.warehouse_service.get_transfer(
            company_id=env.company_id,
            transfer_id=backorders[0].transfer_id,
        )
        assert back_moves[0].product_uom_qty == Decimal("6")


class TestCancel:
    async def test_cancel_releases_reservation(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("10"), Decimal("1"))
        op = env.op_types[StockOperationCode.OUTGOING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("4"),
                    uom_id=env.uom_id,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.reserved_quantity == Decimal("4")
        _ = await env.di.move_engine.cancel_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.reserved_quantity == Decimal("0")
        assert quant.quantity == Decimal("10")


class TestInventory:
    async def test_inventory_gain_writes_gain_layer(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        quant = await _stock_quant(env)
        assert quant is not None
        _ = await env.di.move_engine.inventory_set(
            company_id=env.company_id,
            quant_id=quant.quant_id,
            inventory_quantity=Decimal("8"),
        )
        _ = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("8")
        kinds = {layer.entry_kind for layer in await _layers(env)}
        assert ValueEntryKind.INVENTORY_GAIN in kinds


class TestBarcode:
    async def test_register_resolve_and_conflict(
        self, stock_di, unique_id: str
    ) -> None:
        from apps.stock.models import StockBarcodeEntityType

        company = f"co-{unique_id}"
        service = stock_di.barcode_service
        _ = await service.register(
            company_id=company,
            barcode="4600001",
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id="prod-1",
        )
        resolved = await service.resolve(company_id=company, barcode="4600001")
        assert resolved.entity_id == "prod-1"
        with pytest.raises(PlatformConflictError) as exc_info:
            _ = await service.register(
                company_id=company,
                barcode="4600001",
                entity_type=StockBarcodeEntityType.LOCATION,
                entity_id="loc-9",
            )
        assert exc_info.value.error_code == "barcode_conflict"
        # Идемпотентная повторная регистрация той же сущности — не конфликт.
        _ = await service.register(
            company_id=company,
            barcode="4600001",
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id="prod-1",
        )

    async def test_transfer_barcode_resolves_via_index(
        self, stock_di, unique_id: str
    ) -> None:
        """Штрихкод накладной пишется в индекс атомарно с документом —
        скан на гейте резолвит его без отдельной колонки у transfer."""
        from apps.stock.models import StockBarcodeEntityType

        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        op = env.op_types[StockOperationCode.INCOMING]
        code = f"TRF-{unique_id}"
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=code,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal(1),
                    uom_id=env.uom_id,
                )
            ],
        )
        resolved = await stock_di.barcode_service.resolve(
            company_id=env.company_id, barcode=code
        )
        assert resolved.entity_type == StockBarcodeEntityType.TRANSFER
        assert resolved.entity_id == transfer.transfer_id


class TestIsolation:
    async def test_company_data_is_isolated(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("3"), Decimal("1"))
        other = f"other-{unique_id}"
        quants = await StockQuant.objects.filter(company_id=other).all()
        assert quants == []
        layers = await StockValueLayer.objects.filter(company_id=other).all()
        assert layers == []


class TestPulse:
    async def test_pulse_reports_transfers(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("2"), Decimal("1"))
        pulse = await env.di.pulse_service.warehouse_pulse(
            company_id=env.company_id, warehouse_id=env.warehouse.warehouse_id
        )
        assert pulse.warehouse_id == env.warehouse.warehouse_id
        assert len(pulse.transfers) == 1
        assert pulse.transfers[0].state == StockTransferState.DONE

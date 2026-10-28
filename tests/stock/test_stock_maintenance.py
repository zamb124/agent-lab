"""Фоновые тики stock_worker: reconcile резервов, claims GC,
reorder по min/max, плановый пересчёт (cycle count).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from apps.stock.models import (
    StockMove,
    StockMoveLine,
    StockMoveLineKind,
    StockMoveLineState,
    StockMoveState,
    StockOperationCode,
    StockQuant,
    StockReorderRule,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from core.utils.time import utcnow
from tests.stock.test_stock_domain import (
    StockEnv,
    _make_env,
    _receipt,
)


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
    )


class TestReconcile:
    async def test_fixes_reserved_drift(
        self, stock_di, unique_id: str
    ) -> None:
        """Резерв на quant «уплыл» от суммы открытых строк — тик чинит."""
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("10"), Decimal("5"))
        # Доставка: резерв по открытым строкам появится на quant.
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
                    product_qty=Decimal("3"),
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
        # Ломаем резерв руками (дрейф), затем reconcile чинит.

        quants = await StockQuant.list_unordered_for_warehouse(
            env.company_id, env.warehouse.warehouse_id
        )
        drifted = [q for q in quants if q.reserved_quantity > Decimal("0")]
        assert drifted, "ожидали зарезервированный остаток"
        for q in drifted:
            q.reserved_quantity += Decimal("100")
            _ = await q.save()
        report = await env.di.maintenance_service.reconcile_warehouse(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
        )
        assert report.reserved_fixed >= 1
        for q in await StockQuant.list_unordered_for_warehouse(
            env.company_id, env.warehouse.warehouse_id
        ):
            assert q.reserved_quantity <= Decimal("3")


class TestClaimsGc:
    async def test_releases_stale_claims(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("5"), Decimal("2"))
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
                    product_qty=Decimal("2"),
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

        lines = await StockMoveLine.list_unordered_open_for_warehouse(
            env.company_id, env.warehouse.warehouse_id
        )
        assert lines
        # Имитируем захват, сделанный давно.
        stale_time = utcnow() - timedelta(hours=10)
        for line in lines:
            line.claimed_at = stale_time
            line.assigned_user_id = "worker-1"
            _ = await line.save()
        report = await env.di.maintenance_service.release_stale_claims(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            claimed_before=utcnow() - timedelta(hours=8),
        )
        assert report.released == len(lines)
        for line in await StockMoveLine.list_unordered_open_for_warehouse(
            env.company_id, env.warehouse.warehouse_id
        ):
            assert line.assigned_user_id is None
            assert line.claimed_at is None


class TestReorder:
    async def test_creates_draft_when_below_min(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        incoming = env.op_types[StockOperationCode.INCOMING]
        rule = await StockReorderRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            min_qty=Decimal("5"),
            max_qty=Decimal("20"),
            operation_type_id=incoming.operation_type_id,
        )
        # Пустой склад → под min → тик создаёт draft на max-0=20.
        created = await env.di.maintenance_service.reorder_company(
            company_id=env.company_id
        )
        assert created == 1
        open_moves = await StockMove.list_open_by_origin(
            env.company_id, "reorder_rule", rule.rule_id
        )
        assert len(open_moves) == 1
        assert open_moves[0].product_qty == Decimal("20")
        # Повторный тик — дедуп по открытому move.
        again = await env.di.maintenance_service.reorder_company(
            company_id=env.company_id
        )
        assert again == 0

    async def test_skips_when_above_min(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("50"), Decimal("1"))
        incoming = env.op_types[StockOperationCode.INCOMING]
        _ = await StockReorderRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            min_qty=Decimal("5"),
            max_qty=Decimal("20"),
            operation_type_id=incoming.operation_type_id,
        )
        created = await env.di.maintenance_service.reorder_company(
            company_id=env.company_id
        )
        assert created == 0


class TestCycleCount:
    async def test_schedules_count_lines(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("7"), Decimal("3"))
        # Ячейка ни разу не считалась → попадает в очередь.
        report = await env.di.maintenance_service.cycle_count_warehouse(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            due_before=utcnow(),
            limit=10,
        )
        assert report.bins_scheduled >= 1
        assert report.lines_created >= 1
        count_lines = [
            ln
            for ln in await StockMoveLine.list_unordered_open_for_warehouse(
                env.company_id, env.warehouse.warehouse_id
            )
            if ln.kind == StockMoveLineKind.COUNT
        ]
        assert count_lines
        for ln in count_lines:
            assert ln.state == StockMoveLineState.OPEN
            move = await StockMove.by_id(env.company_id, ln.move_id)
            assert move is not None
            assert move.state == StockMoveState.CONFIRMED
            assert move.origin_document_type == "cycle_count"

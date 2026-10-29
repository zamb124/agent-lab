"""Маршрутные цепочки (push/pull): route+steps, развёртка строки накладной
в плечи waiting, активация следующего плеча после проводки предыдущего.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.stock.models import (
    StockLayoutPreset,
    StockLocationUsage,
    StockMove,
    StockMoveState,
    StockOperationCode,
    StockRemovalStrategy,
    StockTransfer,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.route import StockRouteStepSpec
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from tests.stock.test_stock_domain import StockEnv, _make_env


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
    )


async def _qc_location(env: StockEnv) -> str:
    zone = await env.di.topology_service.create_location(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        parent_id=env.warehouse.view_location_id,
        name="QC zone",
        usage=StockLocationUsage.VIEW,
        barcode=None,
    )
    cell = await env.di.topology_service.create_location(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        parent_id=zone.location_id,
        name="QC cell",
        usage=StockLocationUsage.BIN,
        barcode=None,
    )
    return cell.location_id


class TestRouteCrud:
    async def test_create_and_get(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        internal = env.op_types[StockOperationCode.INTERNAL]
        created = await env.di.rule_service.create_route(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="QC pipeline",
            code="qc",
            steps=[
                StockRouteStepSpec(sequence=10, operation_type_id=internal.operation_type_id),
                StockRouteStepSpec(sequence=20, operation_type_id=internal.operation_type_id),
            ],
        )
        assert created.route_id.startswith("rte_")
        assert [s.sequence for s in created.steps] == [10, 20]
        fetched = await env.di.rule_service.get_route(
            company_id=env.company_id, route_id=created.route_id
        )
        assert fetched.route_id == created.route_id
        assert len(fetched.steps) == 2
        listed = await env.di.rule_service.list_routes(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
        )
        assert [r.route_id for r in listed] == [created.route_id]

    async def test_foreign_operation_type_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        other_wh = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"W2{unique_id[:6]}",
            name="Other",
            owner_user_id="test_user",

            layout_preset=StockLayoutPreset.SIMPLE,

            removal_strategy=StockRemovalStrategy.FIFO,
        )
        other_ops = await env.di.warehouse_service.list_operation_types(
            company_id=env.company_id, warehouse_id=other_wh.warehouse_id
        )
        foreign = next(
            op for op in other_ops if op.code == StockOperationCode.INTERNAL
        )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.rule_service.create_route(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="Broken",
                code="",
                steps=[
                    StockRouteStepSpec(sequence=10, operation_type_id=foreign.operation_type_id)
                ],
            )
        assert exc.value.error_code == "route_step_warehouse_mismatch"

    async def test_missing_route(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            await env.di.rule_service.get_route(
                company_id=env.company_id, route_id="rte_missing"
            )
        assert exc.value.error_code == "route_not_found"


class TestRouteChain:
    async def test_pull_chain_two_legs(
        self, stock_di, unique_id: str
    ) -> None:
        """IN → QC → Stock: плечо 2 спит в waiting и будится после проводки плеча 1."""
        env = await _env(stock_di, unique_id)
        qc_id = await _qc_location(env)
        incoming = env.op_types[StockOperationCode.INCOMING]
        internal = env.op_types[StockOperationCode.INTERNAL]
        route = await env.di.rule_service.create_route(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Receive via QC",
            code="",
            steps=[
                StockRouteStepSpec(
                    sequence=10,
                    operation_type_id=incoming.operation_type_id,
                    dest_location_id=qc_id,
                ),
                StockRouteStepSpec(
                    sequence=20,
                    operation_type_id=internal.operation_type_id,
                    source_location_id=qc_id,
                    dest_location_id=env.warehouse.stock_location_id,
                ),
            ],
        )
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=incoming.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("5"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("10"),
                    route_id=route.route_id,
                )
            ],
        )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        assert len(moves) == 2
        first = next(m for m in moves if m.move_origin_id is None)
        second = next(m for m in moves if m.move_origin_id is not None)
        assert first.state == StockMoveState.DRAFT
        assert first.location_dest_id == qc_id
        assert first.move_dest_id == second.move_id
        assert second.state == StockMoveState.WAITING
        assert second.move_origin_id == first.move_id
        assert second.location_id == qc_id
        assert second.location_dest_id == env.warehouse.stock_location_id
        assert second.route_id == route.route_id

        # confirm+assign: спящее плечо пропускается, резерв ложится только на плечо 1.
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        second_now = await StockMove.by_id(env.company_id, second.move_id)
        assert second_now is not None
        assert second_now.state == StockMoveState.WAITING

        # validate: плечо 1 done → advance_chain будит плечо 2 и резервирует.
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        second_woke = await StockMove.by_id(env.company_id, second.move_id)
        assert second_woke is not None
        # Товар физически уже в QC → резерв на второе плечо положился.
        assert second_woke.state == StockMoveState.ASSIGNED

        # Вторая валидация закрывает плечо 2 — товар в Stock.
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        final = await StockMove.by_id(env.company_id, second.move_id)
        assert final is not None
        assert final.state == StockMoveState.DONE
        fresh = await StockTransfer.by_id(env.company_id, transfer.transfer_id)
        assert fresh is not None
        assert fresh.state.value == "done"

    async def test_empty_route_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        route = await env.di.rule_service.create_route(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Empty",
            code="",
            steps=[],
        )
        incoming = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_type_id=incoming.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type=None,
                origin_document_id=None,
                barcode=None,
                moves=[
                    StockMoveSpec(
                        product_id=env.product.product_id,
                        product_qty=Decimal("1"),
                        uom_id=env.uom_id,
                        route_id=route.route_id,
                    )
                ],
            )
        assert exc.value.error_code == "route_empty"

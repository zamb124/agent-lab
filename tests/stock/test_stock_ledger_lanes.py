"""Инварианты леджера на полосах: идемпотентность, конкурентность, остатки.

Продовый путь: реальный Postgres `platform_stock`, настоящий realtime bus
(`publish_lane_run` доходит до `platform:events`). Изоляция — `company_id` на тест.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest

from apps.stock.models import (
    StockMove,
    StockOperationCode,
    StockQuant,
    StockTransferState,
    ValuationMethod,
    ValueEntryKind,
)
from apps.stock.models.api import StockMoveSpec
from core.errors.boundary import PlatformConflictError
from core.lanes import LaneCommit
from tests.stock.test_stock_domain import StockEnv, _layers, _make_env, _receipt


async def _delivery_transfer(
    env: StockEnv, qty: Decimal, *, key: str | None = None
) -> str:
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
        idempotency_key=key,
        moves=[
            StockMoveSpec(
                product_id=env.product.product_id,
                product_qty=qty,
                uom_id=env.uom_id,
            )
        ],
    )
    return transfer.transfer_id


async def _quant(env: StockEnv) -> StockQuant | None:
    return await StockQuant.by_key(
        company_id=env.company_id,
        product_id=env.product.product_id,
        location_id=env.warehouse.stock_location_id,
        lot_id=None,
        owner_entity_id=None,
    )


class TestLaneIdempotency:
    async def test_create_replay_returns_same_transfer(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        key = uuid.uuid7().hex
        op = env.op_types[StockOperationCode.INCOMING]
        first = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            idempotency_key=key,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("3"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("1"),
                )
            ],
        )
        second = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            idempotency_key=key,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("99"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("1"),
                )
            ],
        )
        assert second.transfer_id == first.transfer_id
        moves = await StockMove.list_for_transfer_by_created_at_asc(env.company_id, first.transfer_id)
        assert len(moves) == 1
        assert moves[0].product_uom_qty == Decimal("3")

    async def test_validate_replay_does_not_double_post(
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
                    product_qty=Decimal("5"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("2"),
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        key = uuid.uuid7().hex
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        done = await env.di.move_engine.validate_transfer(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
            idempotency_key=key,
        )
        replay = await env.di.move_engine.validate_transfer(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
            idempotency_key=key,
        )
        assert replay.transfer_id == done.transfer_id
        quant = await _quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("5")
        layers = await _layers(env)
        assert len(layers) == 1

    async def test_same_key_other_command_conflicts(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        key = uuid.uuid7().hex
        op = env.op_types[StockOperationCode.INCOMING]
        _ = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            idempotency_key=key,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("1"),
                )
            ],
        )
        with pytest.raises(PlatformConflictError) as exc_info:
            _ = await env.di.move_engine.confirm_transfer(
                company_id=env.company_id,
                transfer_id=(await env.di.warehouse_service.list_transfers(
                    company_id=env.company_id,
                    warehouse_id=env.warehouse.warehouse_id,
                    state=None,
                    limit=1,
                    offset=0,
                )).items[0].transfer_id,
                idempotency_key=key,
            )
        assert exc_info.value.error_code == "idempotency_key_reused"


class TestStockInvariants:
    async def test_partial_post_never_oversells(
        self, stock_di, unique_id: str
    ) -> None:
        """Спрос 10 при остатке 4: постится только резерв 4, остаток — backorder."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("4"), Decimal("1"))
        transfer_id = await _delivery_transfer(env, Decimal("10"))
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        done = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        quant = await _quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("0")
        assert done.state == StockTransferState.DONE
        backorders = [
            t
            for t in (
                await env.di.warehouse_service.list_transfers(
                    company_id=env.company_id,
                    warehouse_id=env.warehouse.warehouse_id,
                    state=None,
                    limit=10,
                    offset=0,
                )
            ).items
            if t.backorder_of_id is not None
        ]
        assert len(backorders) == 1

    async def test_done_beyond_reserved_is_impossible(
        self, stock_di, unique_id: str
    ) -> None:
        """`done_quantity` строки > резерва: исходный quant ушёл бы ниже нуля."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("4"), Decimal("1"))
        transfer_id = await _delivery_transfer(env, Decimal("4"))
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        _, _, lines = await env.di.warehouse_service.get_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=lines[0].move_line_id,
            done_quantity=Decimal("6"),
            picked=None,
            lot_id=None,
            location_dest_id=None,
        )
        with pytest.raises(PlatformConflictError) as exc_info:
            _ = await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )
        assert exc_info.value.error_code == "insufficient_stock"
        quant = await _quant(env)
        assert quant is not None
        # Откат целый: резерв не потерян.
        assert quant.quantity == Decimal("4")
        assert quant.reserved_quantity == Decimal("4")

    async def test_allow_negative_location_permits_overissue(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
        )
        _ = await _receipt(env, Decimal("4"), Decimal("1"))
        _ = await env.di.topology_service.update_location(
            company_id=env.company_id,
            location_id=env.warehouse.stock_location_id,
            name=None,
            barcode=None,
            is_active=None,
            allow_negative=True,
        )
        transfer_id = await _delivery_transfer(env, Decimal("4"))
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        # done=7 при резерве 4: списание в минус разрешено флагом локации.
        _, _, lines = await env.di.warehouse_service.get_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=lines[0].move_line_id,
            done_quantity=Decimal("7"),
            picked=None,
            lot_id=None,
            location_dest_id=None,
        )
        done = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer_id
        )
        assert done.state == StockTransferState.DONE
        quant = await _quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("-3")


class TestLaneConcurrency:
    async def test_concurrent_deliveries_serialize_on_warehouse_lane(
        self, stock_di, unique_id: str
    ) -> None:
        """Две доставки по складу параллельно: итог остатка строго консистентен."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("10"), Decimal("5"))

        async def ship(qty: Decimal) -> str:
            transfer_id = await _delivery_transfer(env, qty)
            _ = await env.di.move_engine.confirm_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )
            _ = await env.di.move_engine.assign_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )
            _ = await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )
            return transfer_id

        results = await asyncio.gather(
            ship(Decimal("6")), ship(Decimal("6")), return_exceptions=True
        )
        failures = [r for r in results if isinstance(r, BaseException)]
        assert not failures, failures
        # Резерв честно делит остаток 10: 6 + 4, суммарное списание == остатку.
        quant = await _quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("0")
        layers = await _layers(env)
        outbound = [
            layer for layer in layers if layer.entry_kind == ValueEntryKind.OUTBOUND
        ]
        assert len(outbound) == 2
        posted = sum(-layer.quantity for layer in outbound)
        assert posted == Decimal("10")


class TestCommitEvents:
    async def test_validate_commit_carries_events(
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
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("3"),
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        key = uuid.uuid7().hex
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
            idempotency_key=key,
        )
        commit = await LaneCommit.by_idempotency_key(
            env.company_id, key, using="stock"
        )
        assert commit is not None
        types = {event.type for event in commit.platform_events()}
        assert "stock/move/done" in types
        assert "stock/quant/changed" in types
        assert "stock/transfer/done" in types
        # Быстрый publish_lane_run уже отметил коммит.
        assert commit.published_at is not None

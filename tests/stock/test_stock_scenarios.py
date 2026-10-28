"""Сценарные тесты архетипов складов: пресеты топологии, putaway-правила
(CRUD + владельческие зоны), пополнение цепочкой маршрута, фильтр
остатков по владельцу, каскад auto_validate.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.stock.models import (
    ReflexMode,
    StockLayoutPreset,
    StockLocationUsage,
    StockMove,
    StockMoveLine,
    StockMoveState,
    StockOperationCode,
    StockPartnerRole,
    StockPutawayRule,
    StockPutawayStrategy,
    StockQuant,
    StockRemovalStrategy,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.route import StockRouteStepSpec
from apps.stock.services.company_init_service import virtual_location_id
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from tests.stock.test_stock_domain import StockEnv, _make_env


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
    )


def _location_names(locations) -> set[str]:
    return {loc.name for loc in locations}


class TestPresets:
    """Пресет раскладывает топологию и проводку типовых операций."""

    async def test_dc_topology(self, stock_di, unique_id: str) -> None:
        company = f"co-{unique_id}"
        await stock_di.company_init_service.init_company_stock(
            company_id=company
        )
        wh = await stock_di.warehouse_service.create_warehouse(
            company_id=company,
            code=f"DC{unique_id[:6]}",
            name="Distribution Center",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.DISTRIBUTION_CENTER,

            removal_strategy=StockRemovalStrategy.FIFO,
        )
        locations = await stock_di.topology_service.list_locations(
            company_id=company, warehouse_id=wh.warehouse_id
        )
        names = _location_names(locations)
        assert {
            "Receiving Dock",
            "Quality Control",
            "Storage",
            "Bulk",
            "Forward Pick",
            "Clean Floor",
            "Packing",
            "Shipping Dock",
            "Quarantine",
        } <= names
        by_name = {loc.name: loc for loc in locations}
        assert by_name["Bulk"].parent_id == by_name["Storage"].location_id
        # Основной запас РЦ — forward-зона.
        assert by_name["Forward Pick"].location_id == wh.stock_location_id
        op_types = await stock_di.warehouse_service.list_operation_types(
            company_id=company, warehouse_id=wh.warehouse_id
        )
        incoming = next(
            op for op in op_types if op.code == StockOperationCode.INCOMING
        )
        assert (
            incoming.default_dest_location_id
            == by_name["Receiving Dock"].location_id
        )

    async def test_standard_topology(self, stock_di, unique_id: str) -> None:
        company = f"co-{unique_id}"
        await stock_di.company_init_service.init_company_stock(
            company_id=company
        )
        wh = await stock_di.warehouse_service.create_warehouse(
            company_id=company,
            code=f"DS{unique_id[:6]}",
            name="Dark Store",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.STANDARD,

            removal_strategy=StockRemovalStrategy.FIFO,
        )
        locations = await stock_di.topology_service.list_locations(
            company_id=company, warehouse_id=wh.warehouse_id
        )
        names = _location_names(locations)
        assert {"Receiving", "Stock", "Pick", "Packing", "Shipping"} <= names
        by_name = {loc.name: loc for loc in locations}
        assert by_name["Pick"].location_id == wh.stock_location_id


class TestPutawayRulesCrud:
    async def test_crud_cycle(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        wh_id = env.warehouse.warehouse_id
        created = await env.di.rule_service.create_putaway_rule(
            company_id=env.company_id,
            warehouse_id=wh_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=env.warehouse.stock_location_id,
            product_id=env.product.product_id,
            sequence=10,
        )
        assert created.rule_id.startswith("pur_")
        listed = await env.di.rule_service.list_putaway_rules(
            company_id=env.company_id, warehouse_id=wh_id
        )
        assert [r.rule_id for r in listed] == [created.rule_id]

        updated = await env.di.rule_service.update_putaway_rule(
            company_id=env.company_id,
            rule_id=created.rule_id,
            sequence=5,
            category="frozen",
        )
        assert updated.sequence == 5
        assert updated.category == "frozen"
        assert updated.product_id == env.product.product_id

        paused = await env.di.rule_service.set_putaway_rule_active(
            company_id=env.company_id, rule_id=created.rule_id, is_active=False
        )
        assert paused.is_active is False
        # Неактивное правило не участвует в подборе кандидатов.
        rules = await StockPutawayRule.candidates_for(
            company_id=env.company_id,
            warehouse_id=wh_id,
            product_id=env.product.product_id,
            category="frozen",
            location_ids=[env.warehouse.view_location_id],
        )
        assert rules == []

        deleted = await env.di.rule_service.delete_putaway_rule(
            company_id=env.company_id, rule_id=created.rule_id
        )
        assert deleted.rule_id == created.rule_id
        listed = await env.di.rule_service.list_putaway_rules(
            company_id=env.company_id, warehouse_id=wh_id
        )
        assert listed == []

    async def test_foreign_location_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"W2{unique_id[:6]}",
            name="Other",
            owner_user_id="test_user",

            layout_preset=StockLayoutPreset.SIMPLE,

            removal_strategy=StockRemovalStrategy.FIFO,
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            await env.di.rule_service.create_putaway_rule(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                location_in_id=env.warehouse.view_location_id,
                location_out_id=other.stock_location_id,
            )
        assert exc.value.error_code == "location_not_found"

    async def test_partner_dest_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        partner = virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER, StockPartnerRole.VENDOR
        )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.rule_service.create_putaway_rule(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                location_in_id=env.warehouse.view_location_id,
                location_out_id=partner,
            )
        assert exc.value.error_code == "putaway_rule_bad_location"


class TestOwnerScopedPutaway:
    async def test_owner_rule_matches_only_owner(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        wh_id = env.warehouse.warehouse_id
        # Общее правило + правило владельца A в ту же in-зону.
        generic = await env.di.rule_service.create_putaway_rule(
            company_id=env.company_id,
            warehouse_id=wh_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=env.warehouse.stock_location_id,
            sequence=1,
        )
        owned = await env.di.rule_service.create_putaway_rule(
            company_id=env.company_id,
            warehouse_id=wh_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=env.warehouse.stock_location_id,
            owner_entity_id="ent-owner-a",
            sequence=1,
        )
        matched_owner = await StockPutawayRule.candidates_for(
            company_id=env.company_id,
            warehouse_id=wh_id,
            product_id=env.product.product_id,
            category="",
            location_ids=[env.warehouse.view_location_id],
            owner_entity_id="ent-owner-a",
        )
        # Владелец A видит оба правила, частное идёт впереди общего.
        assert [r.rule_id for r in matched_owner] == [
            owned.rule_id,
            generic.rule_id,
        ]
        matched_other = await StockPutawayRule.candidates_for(
            company_id=env.company_id,
            warehouse_id=wh_id,
            product_id=env.product.product_id,
            category="",
            location_ids=[env.warehouse.view_location_id],
            owner_entity_id="ent-owner-b",
        )
        assert [r.rule_id for r in matched_other] == [generic.rule_id]


class TestReorderRoute:
    async def test_route_draft_chain(self, stock_di, unique_id: str) -> None:
        """Reorder-правило с маршрутом: драфт разворачивается в плечи."""
        env = await _env(stock_di, unique_id)
        internal = env.op_types[StockOperationCode.INTERNAL]
        route = await env.di.rule_service.create_route(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Bulk to forward",
            code="",
            steps=[
                StockRouteStepSpec(
                    sequence=10, operation_type_id=internal.operation_type_id
                ),
                StockRouteStepSpec(
                    sequence=20,
                    operation_type_id=internal.operation_type_id,
                    dest_location_id=env.warehouse.stock_location_id,
                ),
            ],
        )
        rule = await env.di.rule_service.create_reorder_rule(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            min_qty=Decimal("5"),
            max_qty=Decimal("20"),
            operation_type_id=internal.operation_type_id,
            route_id=route.route_id,
        )
        assert rule.route_id == route.route_id

        created = await env.di.maintenance_service.reorder_company(
            company_id=env.company_id
        )
        assert created == 1
        moves = await StockMove.list_open_by_origin(
            env.company_id, "reorder_rule", rule.rule_id
        )
        legs = {m.move_id: m for m in moves}
        assert len(legs) == 2
        first = next(m for m in legs.values() if m.move_origin_id is None)
        second = next(m for m in legs.values() if m.move_origin_id is not None)
        assert first.move_dest_id == second.move_id
        assert second.state == StockMoveState.WAITING
        assert second.location_dest_id == env.warehouse.stock_location_id


class TestQuantsOwnerFilter:
    async def test_filter_by_owner(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        incoming = env.op_types[StockOperationCode.INCOMING]
        for owner in ("ent-owner-a", "ent-owner-b"):
            transfer = await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_type_id=incoming.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=owner,
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
            _ = await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=transfer.transfer_id
            )
        rows_a = await StockQuant.list_by_product_and_location(
            env.company_id,
            location_id=env.warehouse.stock_location_id,
            product_id=env.product.product_id,
            owner_entity_id="ent-owner-a",
            limit=50,
            offset=0,
        )
        assert len(rows_a) == 1
        assert rows_a[0].quantity == Decimal("4")
        total_all = await StockQuant.count_by_location_product_and_owner(
            env.company_id,
            location_id=env.warehouse.stock_location_id,
            product_id=env.product.product_id,
        )
        assert total_all == 2


class TestAutoValidate:
    async def test_confirm_cascades_to_done(
        self, stock_di, unique_id: str
    ) -> None:
        """auto_validate на типе операции: confirm → assign → validate одной командой."""
        env = await _env(stock_di, unique_id)
        outgoing = env.op_types[StockOperationCode.OUTGOING]
        _ = await env.di.warehouse_service.update_operation_type(
            company_id=env.company_id,
            operation_type_id=outgoing.operation_type_id,
            name=None,
            reservation_policy=None,
            backorder_policy=None,
            putaway_mode=None,
            putaway_flow_id=None,
            auto_validate=True,
        )
        # Запас на продажу.
        incoming = env.op_types[StockOperationCode.INCOMING]
        receipt = await env.di.move_engine.create_transfer(
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
                    product_qty=Decimal("10"),
                    uom_id=env.uom_id,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=receipt.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=receipt.transfer_id
        )
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=receipt.transfer_id
        )

        sale = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=outgoing.operation_type_id,
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
        result = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=sale.transfer_id
        )
        assert result.state.value == "done"
        moves = await StockMove.list_for_transfer(
            env.company_id, sale.transfer_id
        )
        assert all(m.state == StockMoveState.DONE for m in moves)
        lines = await StockMoveLine.list_for_moves(
            env.company_id, [m.move_id for m in moves]
        )
        assert all(
            ln.state.value == "done" for ln in lines
        )
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quantity == Decimal("7")


class TestPutawayStrategies:
    """Цепочка ``putaway_strategies`` типа хранения ранжирует подсказки."""

    async def _draft_incoming_move(self, env: StockEnv) -> StockMove:
        incoming = env.op_types[StockOperationCode.INCOMING]
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
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                )
            ],
        )
        moves = await StockMove.list_for_transfer(
            env.company_id, transfer.transfer_id
        )
        return moves[0]

    async def test_strategy_chain_ranks_and_filters(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        wh_id = env.warehouse.warehouse_id
        chain = await env.di.topology_service.create_storage_type(
            company_id=env.company_id,
            warehouse_id=wh_id,
            name=f"Chain {unique_id[:6]}",
            putaway_strategies=[
                StockPutawayStrategy.EXISTING_STOCK,
                StockPutawayStrategy.EMPTY_BIN,
            ],
            allowed_container_type_ids=[],
        )
        manual_t = await env.di.topology_service.create_storage_type(
            company_id=env.company_id,
            warehouse_id=wh_id,
            name=f"Manual {unique_id[:6]}",
            putaway_strategies=[StockPutawayStrategy.MANUAL],
            allowed_container_type_ids=[],
        )
        zone = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh_id,
            parent_id=None,
            name="Zone A",
            usage=StockLocationUsage.VIEW,
            barcode=None,
        )

        async def _bin(name: str, storage_type_id, pick_sequence: int):
            return await env.di.topology_service.create_location(
                company_id=env.company_id,
                warehouse_id=wh_id,
                parent_id=zone.location_id,
                name=name,
                usage=StockLocationUsage.BIN,
                barcode=None,
                storage_type_id=storage_type_id,
                pick_sequence=pick_sequence,
            )

        # «Дальняя» ячейка получит товар; «ближняя» пустая — pick_sequence
        # меньше, но в цепочке existing_stock стоит раньше empty_bin.
        bin_stocked = await _bin("A-far", chain.storage_type_id, 99)
        bin_empty = await _bin("A-near", chain.storage_type_id, 1)
        bin_manual = await _bin("A-manual", manual_t.storage_type_id, 2)

        incoming = env.op_types[StockOperationCode.INCOMING]
        # SHADOW: рефлекс советует, но не переставляет приёмник строки —
        # иначе сама приёмка уедет в ячейку, выбранную стратегией.
        _ = await env.di.warehouse_service.update_operation_type(
            company_id=env.company_id,
            operation_type_id=incoming.operation_type_id,
            name=None,
            reservation_policy=None,
            backorder_policy=None,
            putaway_mode=ReflexMode.SHADOW,
            putaway_flow_id=None,
            auto_validate=None,
        )
        receipt = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=wh_id,
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
                    location_dest_id=bin_stocked.location_id,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=receipt.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=receipt.transfer_id
        )
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=receipt.transfer_id
        )

        move = await self._draft_incoming_move(env)
        suggestions = await env.di.placement_service.suggest(
            company_id=env.company_id,
            warehouse=env.warehouse,
            move=move,
        )
        by_loc = {s.location_id: s.reason_code for s in suggestions}
        # Стратегия бьёт близость: догрузка (existing_stock) первой,
        # хотя у пустой ячейки pick_sequence меньше.
        assert by_loc[bin_stocked.location_id] == "same_product"
        assert by_loc[bin_empty.location_id] == "empty_bin"
        assert bin_manual.location_id not in by_loc
        assert suggestions[0].location_id == bin_stocked.location_id
        assert suggestions[1].location_id == bin_empty.location_id

        with_rejected = await env.di.placement_service.suggest(
            company_id=env.company_id,
            warehouse=env.warehouse,
            move=move,
            include_rejected=True,
        )
        rejected = {
            s.location_id: s.reason_code for s in with_rejected if not s.allowed
        }
        assert rejected[bin_manual.location_id] == "manual"


class TestWalkSequence:
    """``sequence`` строки = ``pick_sequence`` рабочей ячейки,
    ``stop_order`` = позиция накладной в рейсе волны."""

    async def _zone_with_bins(
        self, env: StockEnv, unique_id: str
    ) -> tuple:
        wh_id = env.warehouse.warehouse_id
        zone = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh_id,
            parent_id=None,
            name=f"Zone-{unique_id[:4]}",
            usage=StockLocationUsage.VIEW,
            barcode=None,
        )
        bin_far = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh_id,
            parent_id=zone.location_id,
            name="B-far",
            usage=StockLocationUsage.BIN,
            barcode=None,
            pick_sequence=90,
        )
        bin_near = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh_id,
            parent_id=zone.location_id,
            name="B-near",
            usage=StockLocationUsage.BIN,
            barcode=None,
            pick_sequence=10,
        )
        return zone, bin_far, bin_near

    async def _receipt_to_bin(
        self, env: StockEnv, dest_id: str, qty: Decimal
    ) -> None:
        incoming = env.op_types[StockOperationCode.INCOMING]
        _ = await env.di.warehouse_service.update_operation_type(
            company_id=env.company_id,
            operation_type_id=incoming.operation_type_id,
            name=None,
            reservation_policy=None,
            backorder_policy=None,
            putaway_mode=ReflexMode.SHADOW,
            putaway_flow_id=None,
            auto_validate=None,
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
                    product_qty=qty,
                    uom_id=env.uom_id,
                    location_dest_id=dest_id,
                )
            ],
        )
        for step in ("confirm", "assign", "validate"):
            _ = await getattr(
                env.di.move_engine, f"{step}_transfer"
            )(company_id=env.company_id, transfer_id=transfer.transfer_id)

    async def _outgoing_transfer(
        self, env: StockEnv, source_id: str, qty: Decimal
    ) -> str:
        outgoing = env.op_types[StockOperationCode.OUTGOING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=outgoing.operation_type_id,
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
                    location_id=source_id,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        return transfer.transfer_id

    async def test_line_sequence_follows_pick_order(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        zone, bin_far, bin_near = await self._zone_with_bins(env, unique_id)
        await self._receipt_to_bin(env, bin_far.location_id, Decimal("4"))
        await self._receipt_to_bin(env, bin_near.location_id, Decimal("4"))

        transfer_id = await self._outgoing_transfer(
            env, zone.location_id, Decimal("8")
        )
        moves = await StockMove.list_for_transfer(env.company_id, transfer_id)
        lines = await StockMoveLine.list_for_moves(
            env.company_id, [m.move_id for m in moves]
        )
        # Дальняя ячейка закрыла бы FIFO первой, но sequence строки —
        # порядок обхода: ближняя ячейка (pick_sequence=10) идёт раньше.
        by_loc = {ln.location_id: ln.sequence for ln in lines}
        assert by_loc[bin_near.location_id] == 10
        assert by_loc[bin_far.location_id] == 90
        queue = await StockMoveLine.list_queue(
            env.company_id, env.warehouse.warehouse_id
        )
        assert queue[0].location_id == bin_near.location_id

    async def test_wave_stop_order_dominates_walk(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        zone, bin_far, bin_near = await self._zone_with_bins(env, unique_id)
        await self._receipt_to_bin(env, bin_far.location_id, Decimal("4"))
        await self._receipt_to_bin(env, bin_near.location_id, Decimal("4"))

        # Два заказа: первый снимает из ближней ячейки, второй — из дальней.
        tr_a = await self._outgoing_transfer(env, bin_near.location_id, Decimal("2"))
        tr_b = await self._outgoing_transfer(env, bin_far.location_id, Decimal("2"))
        lines_a = await StockMoveLine.list_for_moves(
            env.company_id,
            [m.move_id for m in await StockMove.list_for_transfer(env.company_id, tr_a)],
        )
        lines_b = await StockMoveLine.list_for_moves(
            env.company_id,
            [m.move_id for m in await StockMove.list_for_transfer(env.company_id, tr_b)],
        )
        # Рейс: остановка B раньше A — строки дальней ячейки идут первыми.
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name=f"RUN-{unique_id[:4]}",
            move_line_ids=[
                *(ln.move_line_id for ln in lines_a),
                *(ln.move_line_id for ln in lines_b),
            ],
            move_ids=[],
            stop_transfer_ids=[tr_b, tr_a],
        )
        assert wave.stops == [tr_b, tr_a]
        queue = await StockMoveLine.list_queue(
            env.company_id, env.warehouse.warehouse_id
        )
        in_wave = [ln for ln in queue if ln.wave_id == wave.wave_id]
        assert in_wave[0].transfer_id == tr_b
        assert in_wave[0].stop_order == 0
        assert in_wave[1].transfer_id == tr_a
        assert in_wave[1].stop_order == 1

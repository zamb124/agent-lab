"""Изоляция арендаторов — чужие данные недоступны и немутируемы.

Бизнес-правило: ``company_id`` — это граница предприятия. Любой id,
выданный компании A (накладная, move, строка задания, quant, партия,
локация, контейнер, склад, слой оценки, штрихкод), для компании B
не существует: ни чтение, ни мутация не должны видеть чужое.
Для денежной системы это первичный инвариант — утечка одного
остатка или слоя оценки между арендаторами ломает учёт обоих.

Здесь проверяется не «модель вернула None», а полная цепочка:
чтение → мутация → резерв → проводка → оценка — на каждом шаге
компания B получает ровно not_found/conflict, без побочных записей.
"""

from decimal import Decimal

import pytest

from apps.stock.models import (
    StockBarcodeEntityType,
    StockContainerKind,
    StockMove,
    StockMoveLine,
    StockOperationCode,
    StockQuant,
    StockTracking,
    StockTransfer,
    StockValueLayer,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.location import StockLocation
from apps.stock.models.lot import StockLot
from core.errors.boundary import PlatformNotFoundError

from .test_stock_domain import StockEnv, _make_env, _receipt


async def _env(stock_di, unique_id: str, tag: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{tag}-{unique_id}", f"{tag}{unique_id}",
        ValuationMethod.FIFO,
    )


async def _outgoing_transfer(env: StockEnv, qty: Decimal) -> str:
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
                unit_price=None,
            )
        ],
    )
    return transfer.transfer_id


class TestReadIsolation:
    """Чтение: чужие id возвращают None на каждой модели."""

    async def test_core_models_invisible_cross_company(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        _ = await _receipt(env_a, Decimal("5"), Decimal("3"))
        tid = await _outgoing_transfer(env_a, Decimal("2"))
        _ = await env_a.di.move_engine.confirm_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        _ = await env_a.di.move_engine.assign_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        move = (
            await StockMove.list_for_transfer_by_created_at_asc(env_a.company_id, tid)
        )[0]
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(env_a.company_id, move.move_id)
        )[0]
        quant = await StockQuant.by_key(
            company_id=env_a.company_id,
            product_id=env_a.product.product_id,
            location_id=env_a.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Партия компании A тоже невидима для B.
        tracked = await env_a.di.catalog_service.create_product(
            company_id=env_a.company_id,
            name=f"LT {unique_id}",
            sku=f"LT-{unique_id}",
            uom_id=env_a.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.LOT,
            is_storable=True,
            category="general",
            barcode=None,
        )
        lot = await env_a.di.catalog_service.create_lot(
            company_id=env_a.company_id,
            product_id=tracked.product_id,
            name=f"LOT-{unique_id}",
            barcode=None,
            expiration_at=None,
        )
        b = env_b.company_id
        assert await StockTransfer.by_id(b, tid) is None
        assert await StockMove.by_id(b, move.move_id) is None
        assert await StockMoveLine.by_id(b, line.move_line_id) is None
        assert await StockLot.by_id(b, lot.lot_id) is None
        assert (
            await StockQuant.by_key(
                company_id=b,
                product_id=env_a.product.product_id,
                location_id=quant.location_id,
                lot_id=None,
                owner_entity_id=None,
            )
            is None
        )
        assert (
            await StockLocation.by_id(b, env_a.warehouse.stock_location_id)
            is None
        )

    async def test_value_layers_isolated(
        self, stock_di, unique_id: str
    ) -> None:
        """Слои оценки — деньги: у B не должно быть видно слоёв A."""
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        _ = await _receipt(env_a, Decimal("5"), Decimal("7"))
        layers_b = await StockValueLayer.list_by_entry_no_asc(
            env_b.company_id,
            product_id=None,
            warehouse_id=None,
            limit=500,
            offset=0,
        )
        assert all(
            layer.company_id == env_b.company_id for layer in layers_b
        )
        # Контроль: у A слой реально записан (иначе тест пустой).
        layers_a = await StockValueLayer.list_by_entry_no_asc(
            env_a.company_id,
            product_id=None,
            warehouse_id=None,
            limit=500,
            offset=0,
        )
        assert layers_a

    async def test_warehouse_list_not_leaking(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        page = await env_b.di.warehouse_service.list_warehouses(
            company_id=env_b.company_id, limit=100, offset=0
        )
        b_ids = {w.warehouse_id for w in page.items}
        assert env_a.warehouse.warehouse_id not in b_ids

    async def test_barcode_namespace_per_company(
        self, stock_di, unique_id: str
    ) -> None:
        """Один и тот же штрихкод в двух компаниях — два разных
        носителя: индекс баркодов тоже изолирован."""
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        code = f"SHARE-{unique_id}"
        _ = await env_a.di.barcode_service.register(
            company_id=env_a.company_id,
            barcode=code,
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id=env_a.product.product_id,
        )
        _ = await env_b.di.barcode_service.register(
            company_id=env_b.company_id,
            barcode=code,
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id=env_b.product.product_id,
        )
        res_b = await env_b.di.barcode_service.resolve(
            company_id=env_b.company_id, barcode=code
        )
        assert res_b.entity_id == env_b.product.product_id


class TestMutationIsolation:
    """Мутации: чужие документы для B не существуют."""

    async def test_transfer_commands_foreign_company(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        _ = await _receipt(env_a, Decimal("5"), Decimal("3"))
        tid = await _outgoing_transfer(env_a, Decimal("2"))
        for verb in ("confirm", "assign", "validate", "cancel"):
            with pytest.raises(PlatformNotFoundError) as exc:
                _ = await getattr(
                    env_b.di.move_engine, f"{verb}_transfer"
                )(company_id=env_b.company_id, transfer_id=tid)
            assert exc.value.error_code == "transfer_not_found"

    async def test_create_transfer_on_foreign_warehouse(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        ops_b = env_b.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env_b.di.move_engine.create_transfer(
                company_id=env_b.company_id,
                warehouse_id=env_a.warehouse.warehouse_id,
                operation_type_id=ops_b.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type=None,
                origin_document_id=None,
                barcode=None,
                moves=[
                    StockMoveSpec(
                        product_id=env_b.product.product_id,
                        product_qty=Decimal("1"),
                        uom_id=env_b.uom_id,
                        unit_price=Decimal("1"),
                    )
                ],
            )
        assert exc.value.error_code == "warehouse_not_found"

    async def test_claim_foreign_line_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        _ = await _receipt(env_a, Decimal("5"), Decimal("3"))
        tid = await _outgoing_transfer(env_a, Decimal("2"))
        _ = await env_a.di.move_engine.confirm_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        _ = await env_a.di.move_engine.assign_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        move = (
            await StockMove.list_for_transfer_by_created_at_asc(env_a.company_id, tid)
        )[0]
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(env_a.company_id, move.move_id)
        )[0]
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env_b.di.task_service.claim(
                company_id=env_b.company_id,
                warehouse_id=env_b.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-b",
            )
        assert exc.value.error_code == "move_line_not_found"

    async def test_scan_commit_foreign_move(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        _ = await _receipt(env_a, Decimal("5"), Decimal("3"))
        tid = await _outgoing_transfer(env_a, Decimal("2"))
        _ = await env_a.di.move_engine.confirm_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        move = (
            await StockMove.list_for_transfer_by_created_at_asc(env_a.company_id, tid)
        )[0]
        from apps.stock.models.scan import (
            ScanContext,
            ScanFlow,
            ScanLineDraft,
        )
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env_b.product.product_id,
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env_b.di.scan_service.commit(
                company_id=env_b.company_id,
                move_id=move.move_id,
                context=ctx,
                actor_user_id="op-b",
            )
        assert exc.value.error_code == "move_not_found"

    async def test_move_container_foreign_company(
        self, stock_di, unique_id: str
    ) -> None:
        """Тара компании A для B не существует — и как источник,
        и как приёмник межкомпанийский переезд невозможен."""
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        ctype = await env_a.di.topology_service.create_container_type(
            company_id=env_a.company_id,
            warehouse_id=env_a.warehouse.warehouse_id,
            name=f"CT-{unique_id}",
            kind=StockContainerKind.PALLET,
            allowed_parent_type_ids=[],
            is_reusable=True,
        )
        pallet = await env_a.di.topology_service.create_container(
            company_id=env_a.company_id,
            warehouse_id=env_a.warehouse.warehouse_id,
            parent_location_id=env_a.warehouse.stock_location_id,
            container_type_id=ctype.container_type_id,
            name=f"PLT-{unique_id}",
            barcode=None,
        )
        # Чужой контейнер → not_found до всякой проверки приёмника.
        with pytest.raises(PlatformNotFoundError):
            _ = await env_b.di.topology_service.move_container(
                company_id=env_b.company_id,
                container_id=pallet.location_id,
                dest_location_id=env_b.warehouse.stock_location_id,
                user_id="op-b",
            )
        # Своя тара на чужой приёмник — тоже not_found.
        ctype_b = await env_b.di.topology_service.create_container_type(
            company_id=env_b.company_id,
            warehouse_id=env_b.warehouse.warehouse_id,
            name=f"CT-{unique_id}",
            kind=StockContainerKind.PALLET,
            allowed_parent_type_ids=[],
            is_reusable=True,
        )
        pallet_b = await env_b.di.topology_service.create_container(
            company_id=env_b.company_id,
            warehouse_id=env_b.warehouse.warehouse_id,
            parent_location_id=env_b.warehouse.stock_location_id,
            container_type_id=ctype_b.container_type_id,
            name=f"PLT-{unique_id}",
            barcode=None,
        )
        with pytest.raises(PlatformNotFoundError):
            _ = await env_b.di.topology_service.move_container(
                company_id=env_b.company_id,
                container_id=pallet_b.location_id,
                dest_location_id=env_a.warehouse.stock_location_id,
                user_id="op-b",
            )

    async def test_count_commit_foreign_location(
        self, stock_di, unique_id: str
    ) -> None:
        """Пересчёт B на ячейке A: локация не найдена, фантомный
        quant на чужом складе не создаётся."""
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        from apps.stock.models.scan import (
            ScanContext,
            ScanFlow,
            ScanLineDraft,
        )
        ctx = ScanContext(
            flow=ScanFlow.COUNT,
            lines=(
                ScanLineDraft(
                    location_id=env_a.warehouse.stock_location_id,
                    location_dest_id=None,
                    product_id=env_b.product.product_id,
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env_b.di.scan_service.inventory_count_commit(
                company_id=env_b.company_id,
                warehouse_id=env_b.warehouse.warehouse_id,
                context=ctx,
                actor_user_id="op-b",
            )
        assert exc.value.error_code == "location_not_found"
        phantom = await StockQuant.objects.filter(
            company_id=env_b.company_id,
            location_id=env_a.warehouse.stock_location_id,
        ).first()
        assert phantom is None

    async def test_wave_foreign_lines_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env_a = await _env(stock_di, unique_id, "a")
        env_b = await _env(stock_di, unique_id, "b")
        _ = await _receipt(env_a, Decimal("5"), Decimal("3"))
        tid = await _outgoing_transfer(env_a, Decimal("2"))
        _ = await env_a.di.move_engine.confirm_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        _ = await env_a.di.move_engine.assign_transfer(
            company_id=env_a.company_id, transfer_id=tid
        )
        move = (
            await StockMove.list_for_transfer_by_created_at_asc(env_a.company_id, tid)
        )[0]
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(env_a.company_id, move.move_id)
        )[0]
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env_b.di.wave_service.create(
                company_id=env_b.company_id,
                warehouse_id=env_b.warehouse.warehouse_id,
                name="W-X",
                move_line_ids=[line.move_line_id],
                move_ids=[],
            )
        assert exc.value.error_code == "move_line_not_found"

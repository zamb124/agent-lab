"""Тесты скан-движка ТСД: чистая машина потоков + атомарный коммит.

Машина (`apps/stock/models/scan.py`) — чистая: тесты прогоняют потоки
без БД. Коммит (`post_lines_in_lane`) проверяется интеграционно:
реальный Postgres, резервная строка сплитится, остатки двигаются.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.stock.models import (
    StockMove,
    StockMoveState,
    StockOperationCode,
    StockQuant,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.scan import (
    ScanContext,
    ScanEntityKind,
    ScanError,
    ScanFlow,
    ScanLineDraft,
    ScanResolution,
    ScanStep,
    scan_commit_ready,
    scan_quantity,
    scan_step,
)
from tests.stock.test_stock_domain import _make_env

_COMPANY = "system"


def _res(
    kind: ScanEntityKind,
    entity_id: str | None,
    *,
    barcode: str = "",
    product_id: str | None = None,
    lot_id: str | None = None,
    serial: str | None = None,
    quantity: Decimal | None = None,
    packaging_id: str | None = None,
    packaging_qty: Decimal | None = None,
) -> ScanResolution:
    return ScanResolution(
        entity_kind=kind,
        entity_id=entity_id,
        barcode=barcode,
        product_id=product_id,
        lot_id=lot_id,
        serial=serial,
        quantity=quantity,
        packaging_id=packaging_id,
        packaging_qty=packaging_qty,
    )


class TestScanMachine:
    """Чистые переходы потоков без БД."""

    def test_receive_full_flow(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        # product → dest → quantity → строка в lines, шаг REVIEW.
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "prod-1"))
        assert r.error is None and r.context.step == ScanStep.DEST
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-1"))
        assert r.error is None and r.context.step == ScanStep.QUANTITY
        r = scan_quantity(r.context, Decimal("5"))
        assert r.error is None
        assert r.context.step == ScanStep.REVIEW
        assert len(r.context.lines) == 1
        line = r.context.lines[0]
        assert line.product_id == "prod-1"
        assert line.location_dest_id == "bin-1"
        assert line.quantity == Decimal("5")

    def test_move_requires_source_location(self) -> None:
        ctx = ScanContext(flow=ScanFlow.MOVE)
        # Первый шаг — LOCATION: товар раньше ячейки отвергается.
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "prod-1"))
        assert r.error == ScanError.UNEXPECTED_STEP
        assert r.context.step == ScanStep.LOCATION  # ждёт ячейку
        assert r.context.product_id is None  # слоты не тронуты

        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        assert r.context.step == ScanStep.PRODUCT
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "prod-1"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-b"))
        r = scan_quantity(r.context, Decimal("2"))
        assert r.error is None
        assert r.context.lines[0].location_id == "bin-a"
        assert r.context.lines[0].location_dest_id == "bin-b"

    def test_pick_without_dest(self) -> None:
        # Отбор: ячейка → товар → количество, приёмника нет.
        ctx = ScanContext(flow=ScanFlow.PICK)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "prod-1"))
        r = scan_quantity(r.context, Decimal("3"))
        assert r.error is None
        assert r.context.lines[0].location_dest_id is None

    def test_container_move_uses_slots(self) -> None:
        ctx = ScanContext(flow=ScanFlow.CONTAINER_MOVE)
        r = scan_step(ctx, _res(ScanEntityKind.CONTAINER, "pallet-1"))
        assert r.context.step == ScanStep.DEST
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-9"))
        assert r.error is None and r.context.step == ScanStep.REVIEW
        assert scan_commit_ready(r.context) is None
        # Строки не набираются — слоты держат тару и приёмник.
        assert not r.context.lines
        assert r.context.container_id == "pallet-1"
        assert r.context.dest_id == "bin-9"

    def test_container_move_not_ready(self) -> None:
        ctx = ScanContext(flow=ScanFlow.CONTAINER_MOVE)
        r = scan_step(ctx, _res(ScanEntityKind.CONTAINER, "pallet-1"))
        assert scan_commit_ready(r.context) == ScanError.NOTHING_TO_COMMIT

    def test_pack_flow(self) -> None:
        ctx = ScanContext(flow=ScanFlow.PACK)
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "prod-1"))
        r = scan_step(r.context, _res(ScanEntityKind.CONTAINER, "box-1"))
        # Количество обязательно — «сколько штук кладём в короб».
        assert r.error is None and r.context.step == ScanStep.QUANTITY
        r = scan_quantity(r.context, Decimal("3"))
        assert r.error is None and r.context.step == ScanStep.REVIEW
        # Тара — локация-приёмник: «положить товар в короб» ≠ «перевезти короб».
        assert r.context.lines[0].location_dest_id == "box-1"
        assert r.context.lines[0].quantity == Decimal("3")
        assert r.context.lines[0].container_id is None

    def test_count_flow(self) -> None:
        ctx = ScanContext(flow=ScanFlow.COUNT)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "prod-1"))
        r = scan_quantity(r.context, Decimal("7"))
        assert r.error is None
        assert r.context.lines[0].quantity == Decimal("7")
        assert scan_commit_ready(r.context) is None

    def test_lot_scan_fills_product_and_lot(self) -> None:
        # Штрихкод партии несёт товар в себе (GS1 lot → product).
        ctx = ScanContext(flow=ScanFlow.PICK)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(
            r.context,
            _res(
                ScanEntityKind.LOT,
                "lot-77",
                product_id="prod-1",
                lot_id="lot-77",
            ),
        )
        assert r.error is None
        assert r.context.product_id == "prod-1"
        assert r.context.lot_id == "lot-77"

    def test_packaging_scan_keeps_product_id(self) -> None:
        # Фасовка «короб 24»: entity_id — упаковка, товар — из справочника.
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(
            ctx,
            _res(
                ScanEntityKind.PACKAGING,
                "pack-1",
                product_id="prod-1",
                packaging_id="pack-1",
                packaging_qty=Decimal("24"),
            ),
        )
        assert r.context.product_id == "prod-1"
        assert r.context.packaging_id == "pack-1"
        assert r.context.quantity == Decimal("24")

    def test_review_accepts_next_product(self) -> None:
        # Многострочная приёмка: после строки поток ждёт следующий товар.
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "prod-1"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-1"))
        r = scan_quantity(r.context, Decimal("1"))
        assert r.context.step == ScanStep.REVIEW
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "prod-2"))
        assert r.error is None and r.context.step == ScanStep.DEST

    def test_wrong_entity_rejected(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(ctx, _res(ScanEntityKind.CONTAINER, "pallet-1"))
        assert r.error == ScanError.UNEXPECTED_STEP

    def test_unknown_barcode(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(ctx, _res(ScanEntityKind.UNKNOWN, None, barcode="???"))
        assert r.error == ScanError.NOT_FOUND

    def test_quantity_not_on_wrong_step(self) -> None:
        ctx = ScanContext(flow=ScanFlow.MOVE)
        r = scan_quantity(ctx, Decimal("5"))
        assert r.error == ScanError.UNEXPECTED_STEP

    def test_zero_quantity_rejected(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "p"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "b"))
        r = scan_quantity(r.context, Decimal("0"))
        assert r.error == ScanError.QUANTITY_REQUIRED

    def test_inquiry_always_done(self) -> None:
        ctx = ScanContext(flow=ScanFlow.INQUIRY)
        r = scan_step(ctx, _res(ScanEntityKind.CONTAINER, "pallet-9"))
        assert r.error is None and r.context.step == ScanStep.DONE

    def test_commit_ready_requires_lines(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        assert scan_commit_ready(ctx) == ScanError.NOTHING_TO_COMMIT
        ctx = ScanContext(
            flow=ScanFlow.RECEIVE,
            lines=(
                ScanLineDraft(
                    location_id=None,
                    location_dest_id="bin-1",
                    product_id="p",
                    quantity=Decimal("1"),
                ),
            ),
        )
        assert scan_commit_ready(ctx) is None


class TestScanCommit:
    """Атомарная проводка набранных строк через реальный Postgres."""

    @pytest.mark.asyncio
    async def test_commit_splits_reserved_line_and_posts(
        self, stock_di, unique_id: str
    ) -> None:
        company = f"co-{unique_id}"
        env = await _make_env(
            stock_di, company, unique_id, ValuationMethod.FIFO
        )
        wh = env.warehouse.warehouse_id

        # Приёмка 10 шт через обычный цикл — товар в stock.
        op_in = env.op_types[StockOperationCode.INCOMING]
        receipt = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_type_id=op_in.operation_type_id,
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
        for verb in ("confirm", "assign", "validate"):
            await getattr(env.di.move_engine, f"{verb}_transfer")(
                company_id=env.company_id,
                transfer_id=receipt.transfer_id,
            )

        # Исходящая накладная на 10 шт: confirm+assign → резерв.
        op_out = env.op_types[StockOperationCode.OUTGOING]
        delivery = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_type_id=op_out.operation_type_id,
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
                    unit_price=None,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=delivery.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=delivery.transfer_id
        )
        moves = await StockMove.list_for_transfer(
            env.company_id, delivery.transfer_id
        )
        move = moves[0]

        # Оператор отсканировал 4 шт: контекст с одной строкой.
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("4"),
                ),
            ),
        )
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx,
            actor_user_id="test_user",
        )
        # Частичный коммит: move ещё открыт, резерв остатка 6 шт.
        assert posted.state != StockMoveState.DONE
        quant = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
        ).first()
        assert quant is not None
        assert quant.quantity == Decimal("6")
        assert quant.reserved_quantity == Decimal("6")

        # Второй коммит на остаток → move done.
        ctx2 = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("6"),
                ),
            ),
        )
        posted2 = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx2,
            actor_user_id="test_user",
        )
        assert posted2.state == StockMoveState.DONE
        quant2 = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
        ).first()
        assert quant2 is not None
        assert quant2.quantity == Decimal("0")
        assert quant2.reserved_quantity == Decimal("0")


class TestWavesAndExceptions:
    """Волны сборки и исключения по заданиям — реальный Postgres."""

    @pytest.mark.asyncio
    async def test_wave_claim_release_exception(
        self, stock_di, unique_id: str
    ) -> None:
        from apps.stock.models import (
            StockMoveLine,
            StockMoveLineKind,
            StockWaveState,
        )
        from core.errors.boundary import PlatformConflictError

        company = f"co-{unique_id}"
        env = await _make_env(stock_di, company, unique_id, ValuationMethod.FIFO)
        wh = env.warehouse.warehouse_id

        # Приёмка 10 шт, затем исходящая на 6 — строка резерва в очереди.
        op_in = env.op_types[StockOperationCode.INCOMING]
        receipt = await env.di.move_engine.create_transfer(
            company_id=company,
            warehouse_id=wh,
            operation_type_id=op_in.operation_type_id,
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
        for verb in ("confirm", "assign", "validate"):
            await getattr(env.di.move_engine, f"{verb}_transfer")(
                company_id=company, transfer_id=receipt.transfer_id
            )
        op_out = env.op_types[StockOperationCode.OUTGOING]
        delivery = await env.di.move_engine.create_transfer(
            company_id=company,
            warehouse_id=wh,
            operation_type_id=op_out.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("6"),
                    uom_id=env.uom_id,
                    unit_price=None,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=company, transfer_id=delivery.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=company, transfer_id=delivery.transfer_id
        )

        queue = await env.di.task_service.queue(
            company_id=company, warehouse_id=wh
        )
        assert len(queue) == 1
        line = queue[0]
        assert line.quantity == Decimal("6")

        # Волна из строки: draft → released.
        wave = await env.di.wave_service.create(
            company_id=company,
            warehouse_id=wh,
            name="WAVE-T1",
            move_line_ids=[line.move_line_id],
            move_ids=[],
            priority=5,
            user_id=None,
            actor_user_id="mgr",
        )
        assert wave.state == StockWaveState.DRAFT
        wave = await env.di.wave_service.release(
            company_id=company,
            warehouse_id=wh,
            wave_id=wave.wave_id,
            actor_user_id="mgr",
        )
        assert wave.state == StockWaveState.RELEASED
        line = await StockMoveLine.by_id(company, line.move_line_id)
        assert line is not None and line.wave_id == wave.wave_id
        assert line.priority == 5

        # Захват оператором → чужой захват отклоняется → release.
        claimed = await env.di.task_service.claim(
            company_id=company,
            warehouse_id=wh,
            move_line_ids=[line.move_line_id],
            user_id="op-1",
        )
        assert claimed.assigned_user_id == "op-1"
        with pytest.raises(PlatformConflictError):
            await env.di.task_service.claim(
                company_id=company,
                warehouse_id=wh,
                move_line_ids=[line.move_line_id],
                user_id="op-2",
            )
        _ = await env.di.task_service.release(
            company_id=company,
            warehouse_id=wh,
            move_line_ids=[line.move_line_id],
            user_id="op-1",
            actor_user_id="op-1",
        )

        # Исключение «недостача 2»: строка 6→4, резерв 6→4,
        # появилось задание пересчёта той же ячейки.
        exc = await env.di.task_service.report_exception(
            company_id=company,
            warehouse_id=wh,
            move_line_id=line.move_line_id,
            shortage=Decimal("2"),
            reason="not_on_shelf",
            actor_user_id="op-1",
        )
        line = await StockMoveLine.by_id(company, line.move_line_id)
        assert line is not None and line.quantity == Decimal("4")
        count_line = await StockMoveLine.by_id(company, exc.count_line_id)
        assert count_line is not None
        assert count_line.kind == StockMoveLineKind.COUNT
        quant = await StockQuant.objects.filter(
            company_id=company,
            product_id=env.product.product_id,
            location_id=line.location_id,
        ).first()
        assert quant is not None
        assert quant.reserved_quantity == Decimal("4")
        assert quant.quantity == Decimal("10")

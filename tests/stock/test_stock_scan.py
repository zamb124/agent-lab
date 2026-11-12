"""Тесты скан-движка ТСД: чистая машина потоков + атомарный коммит.

Машина (`apps/stock/models/scan.py`) — чистая: тесты прогоняют потоки
без БД. Коммит (`post_lines_in_lane`) проверяется интеграционно:
реальный Postgres, резервная строка сплитится, остатки двигаются.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.stock.models import (
    StockLayoutPreset,
    StockLocationUsage,
    StockMove,
    StockMoveLine,
    StockMoveLineKind,
    StockMoveState,
    StockOperationCode,
    StockQuant,
    StockRemovalStrategy,
    StockTracking,
    StockTransferState,
    ValuationMethod,
)
from apps.stock.models.common import STOCK_DB, StockMoveSpec
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
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from tests.stock.test_stock_domain import _make_env, _receipt

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

    def test_label_quantity_skips_qty_step(self) -> None:
        # Количество приехало с меткой (GS1 AI 37): шаг ввода числа
        # пропускается — «подтвердить 5» не требуется.
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(
            ctx,
            _res(ScanEntityKind.PRODUCT, "prod-1", quantity=Decimal("5")),
        )
        assert r.context.step == ScanStep.DEST
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-1"))
        assert r.error is None and r.context.step == ScanStep.REVIEW
        assert len(r.context.lines) == 1
        assert r.context.lines[0].quantity == Decimal("5")

    def test_prefilled_product_skips_product_step(self) -> None:
        # Действие карточки сущности («переместить этот товар») входит
        # в поток с уже заполненным товаром: шаг PRODUCT пропускается.
        ctx = ScanContext(
            flow=ScanFlow.COUNT,
            step=ScanStep.LOCATION,
            product_id="prod-1",
        )
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        assert r.error is None and r.context.step == ScanStep.QUANTITY
        r = scan_quantity(r.context, Decimal("7"))
        assert r.error is None and r.context.step == ScanStep.REVIEW
        assert r.context.lines[0].product_id == "prod-1"
        assert r.context.lines[0].location_id == "bin-a"

    def test_serial_scan_skips_qty_not_dest(self) -> None:
        # Серийник несёт количество 1: шаг числа пропускается, а
        # приёмник подтверждается повторным сканом ячейки — направление
        # всегда явное (та же ячейка — тот же маршрут, другая — новый).
        ctx = ScanContext(
            flow=ScanFlow.RECEIVE,
            step=ScanStep.DEST,
            product_id="prod-1",
        )
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-1"))
        assert r.context.step == ScanStep.QUANTITY
        r = scan_quantity(r.context, Decimal("1"))
        assert r.context.step == ScanStep.REVIEW
        # Второй серийник с REVIEW: товар → ячейка → строка без нампада.
        r = scan_step(
            r.context,
            _res(
                ScanEntityKind.PRODUCT,
                "prod-1",
                lot_id="sn-2",
                serial="SN-2",
                quantity=Decimal("1"),
            ),
        )
        assert r.error is None and r.context.step == ScanStep.DEST
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-1"))
        assert r.error is None and r.context.step == ScanStep.REVIEW
        assert len(r.context.lines) == 2
        assert r.context.lines[1].serial == "SN-2"
        assert r.context.lines[1].location_dest_id == "bin-1"

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
        moves = await StockMove.list_for_transfer_by_created_at_asc(
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
            StockMoveLineState,
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

        # Задание пересчёта закрывается фактом подсчёта той же ячейки
        # и товара — иначе задача навсегда висела бы в очереди.
        ctx = ScanContext(
            flow=ScanFlow.COUNT,
            lines=(
                ScanLineDraft(
                    location_id=line.location_id,
                    location_dest_id=None,
                    product_id=env.product.product_id,
                    quantity=Decimal("8"),
                ),
            ),
        )
        _ = await env.di.scan_service.inventory_count_commit(
            company_id=company,
            warehouse_id=wh,
            context=ctx,
            actor_user_id="op-1",
        )
        count_line = await StockMoveLine.by_id(company, exc.count_line_id)
        assert count_line is not None
        assert count_line.state == StockMoveLineState.DONE
        assert count_line.done_by_user_id == "op-1"


async def _open_transfer(env, code: StockOperationCode, qty: Decimal) -> str:
    """confirm+assign накладной → transfer_id с открытой строкой."""
    op = env.op_types[code]
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
    _ = await env.di.move_engine.confirm_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    _ = await env.di.move_engine.assign_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    return transfer.transfer_id


class TestScanOpenSession:
    """Doc-driven вход в скан-сессию: backend выбирает поток по документу."""

    @pytest.mark.asyncio
    async def test_open_incoming_gives_receive(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_transfer(
            env, StockOperationCode.INCOMING, Decimal("5")
        )
        move, context = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=None,
            transfer_id=transfer_id,
            user_id="op",
        )
        assert context.flow == ScanFlow.RECEIVE
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer_id
        )
        assert move.move_id == moves[0].move_id

    @pytest.mark.asyncio
    async def test_open_outgoing_gives_pick(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("8"), Decimal("2"))
        transfer_id = await _open_transfer(
            env, StockOperationCode.OUTGOING, Decimal("3")
        )
        _, context = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=None,
            transfer_id=transfer_id,
            user_id="op",
        )
        assert context.flow == ScanFlow.PICK

    @pytest.mark.asyncio
    async def test_open_internal_gives_move(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("8"), Decimal("2"))
        transfer_id = await _open_transfer(
            env, StockOperationCode.INTERNAL, Decimal("2")
        )
        _, context = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=None,
            transfer_id=transfer_id,
            user_id="op",
        )
        assert context.flow == ScanFlow.MOVE

    @pytest.mark.asyncio
    async def test_document_barcode_resolves_and_opens(
        self, stock_di, unique_id: str
    ) -> None:
        """Скан накладной: индекс → DOCUMENT → open по transfer_id."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        op = env.op_types[StockOperationCode.INCOMING]
        barcode = f"DOC-{unique_id}"
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=barcode,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("5"),
                    uom_id=env.uom_id,
                    unit_price=None,
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        resolution = await env.di.scan_service.resolve(
            company_id=env.company_id, barcode=barcode
        )
        assert resolution.entity_kind == ScanEntityKind.DOCUMENT
        assert resolution.entity_id == transfer.transfer_id
        move, context = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=None,
            transfer_id=resolution.entity_id,
            user_id="op",
        )
        assert context.flow == ScanFlow.RECEIVE
        assert move.transfer_id == transfer.transfer_id

    @pytest.mark.asyncio
    async def test_open_by_move_id(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_transfer(
            env, StockOperationCode.INCOMING, Decimal("5")
        )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer_id
        )
        move, context = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=moves[0].move_id,
            transfer_id=None,
            user_id="op",
        )
        assert move.move_id == moves[0].move_id
        assert context.flow == ScanFlow.RECEIVE

    @pytest.mark.asyncio
    async def test_open_requires_an_id(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.open_session(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_id=None,
                transfer_id=None,
                user_id="op",
            )
        assert exc.value.error_code == "scan_open_input_invalid"

    @pytest.mark.asyncio
    async def test_open_done_transfer_has_no_work(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _receipt(env, Decimal("5"), Decimal("2"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.open_session(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_id=None,
                transfer_id=transfer_id,
                user_id="op",
            )
        assert exc.value.error_code == "document_no_work"

    @pytest.mark.asyncio
    async def test_open_move_from_other_warehouse(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_transfer(
            env, StockOperationCode.INCOMING, Decimal("5")
        )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer_id
        )
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WHX{unique_id[:6]}",
            name=f"Other {unique_id}",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.open_session(
                company_id=env.company_id,
                warehouse_id=other.warehouse_id,
                move_id=moves[0].move_id,
                transfer_id=None,
                user_id="op",
            )
        assert exc.value.error_code == "move_not_found"

    @pytest.mark.asyncio
    async def test_open_picks_move_with_open_lines(
        self, stock_di, unique_id: str
    ) -> None:
        """Накладная с двумя move: первый закрыт — сессия открывает второй."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        second = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"Widget B {unique_id}",
            sku=f"SKUB-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
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
                    product_qty=Decimal("4"),
                    uom_id=env.uom_id,
                    unit_price=None,
                ),
                StockMoveSpec(
                    product_id=second.product_id,
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                    unit_price=None,
                ),
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        assert len(moves) == 2
        # Закрываем первый move вручную — сессия должна перескочить на второй.
        _ = await StockMove.objects.filter(
            company_id=env.company_id, move_id=moves[0].move_id
        ).update(using=STOCK_DB, state=StockMoveState.DONE)
        _ = await StockMoveLine.objects.filter(
            company_id=env.company_id, move_id=moves[0].move_id
        ).update(using=STOCK_DB, state=StockMoveState.DONE)
        move, context = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=None,
            transfer_id=transfer.transfer_id,
            user_id="op",
        )
        assert move.move_id == moves[1].move_id
        assert context.flow == ScanFlow.RECEIVE

    @pytest.mark.asyncio
    async def test_session_flow_task_kinds(self, stock_di, unique_id: str) -> None:
        """kind строки сильнее типа операции: тара → container_move,
        пересчёт → count на любом документе."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_transfer(
            env, StockOperationCode.INCOMING, Decimal("5")
        )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer_id
        )
        move = moves[0]
        assert (
            await env.di.scan_service._session_flow(
                env.company_id, move, StockMoveLineKind.CONTAINER
            )
            == ScanFlow.CONTAINER_MOVE
        )
        assert (
            await env.di.scan_service._session_flow(
                env.company_id, move, StockMoveLineKind.COUNT
            )
            == ScanFlow.COUNT
        )
        assert (
            await env.di.scan_service._session_flow(
                env.company_id, move, StockMoveLineKind.QUANTITY
            )
            == ScanFlow.RECEIVE
        )


class TestAdhocCommit:
    """Ad-hoc коммит без документа — сессия пишет накладную сама."""

    @pytest.mark.asyncio
    async def test_adhoc_receive_creates_done_transfer(
        self, stock_di, unique_id: str
    ) -> None:
        """«Принять без наряда»: контекст → INCOMING накладная → quant."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh = env.warehouse.warehouse_id
        ctx = ScanContext(
            flow=ScanFlow.RECEIVE,
            lines=(
                ScanLineDraft(
                    location_id=None,
                    location_dest_id=env.warehouse.stock_location_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("5"),
                ),
            ),
        )
        transfer = await env.di.scan_service.commit_adhoc(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_code=StockOperationCode.INCOMING,
            context=ctx,
            actor_user_id="test_user",
        )
        assert transfer.state == StockTransferState.DONE
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        assert len(moves) == 1
        assert moves[0].state == StockMoveState.DONE
        quant = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
        ).first()
        assert quant is not None
        assert quant.quantity == Decimal("5")

    @pytest.mark.asyncio
    async def test_adhoc_internal_move_between_bins(
        self, stock_di, unique_id: str
    ) -> None:
        """«Переместить»: остаток уезжает из стока в ячейку приёмника."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh = env.warehouse.warehouse_id
        _ = await _receipt(env, Decimal("10"), Decimal("2"))
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-ADH-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        ctx = ScanContext(
            flow=ScanFlow.MOVE,
            lines=(
                ScanLineDraft(
                    location_id=env.warehouse.stock_location_id,
                    location_dest_id=bin_b.location_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("4"),
                ),
            ),
        )
        transfer = await env.di.scan_service.commit_adhoc(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_code=StockOperationCode.INTERNAL,
            context=ctx,
            actor_user_id="test_user",
        )
        assert transfer.state == StockTransferState.DONE
        src = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
        ).first()
        dst = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=bin_b.location_id,
        ).first()
        assert src is not None and src.quantity == Decimal("6")
        assert dst is not None and dst.quantity == Decimal("4")

    @pytest.mark.asyncio
    async def test_adhoc_multi_product_one_transfer(
        self, stock_di, unique_id: str
    ) -> None:
        """Несколько товаров в одном коммите — один документ, move на товар."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh = env.warehouse.warehouse_id
        second = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"Widget B {unique_id}",
            sku=f"SKUB-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
        )
        op = env.op_types[StockOperationCode.INCOMING]
        receipt = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=wh,
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
                    unit_price=Decimal("2"),
                ),
                StockMoveSpec(
                    product_id=second.product_id,
                    product_qty=Decimal("8"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("3"),
                ),
            ],
        )
        for verb in ("confirm", "assign", "validate"):
            _ = await getattr(env.di.move_engine, f"{verb}_transfer")(
                company_id=env.company_id, transfer_id=receipt.transfer_id
            )
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-MULTI-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        ctx = ScanContext(
            flow=ScanFlow.MOVE,
            lines=(
                ScanLineDraft(
                    location_id=env.warehouse.stock_location_id,
                    location_dest_id=bin_b.location_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("3"),
                ),
                ScanLineDraft(
                    location_id=env.warehouse.stock_location_id,
                    location_dest_id=bin_b.location_id,
                    product_id=second.product_id,
                    quantity=Decimal("7"),
                ),
            ),
        )
        transfer = await env.di.scan_service.commit_adhoc(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_code=StockOperationCode.INTERNAL,
            context=ctx,
            actor_user_id="test_user",
        )
        assert transfer.state == StockTransferState.DONE
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        assert len(moves) == 2
        assert {move.state for move in moves} == {StockMoveState.DONE}
        for product_id, expected in (
            (env.product.product_id, Decimal("3")),
            (second.product_id, Decimal("7")),
        ):
            quant = await StockQuant.objects.filter(
                company_id=env.company_id,
                product_id=product_id,
                location_id=bin_b.location_id,
            ).first()
            assert quant is not None
            assert quant.quantity == expected

    @pytest.mark.asyncio
    async def test_adhoc_empty_context_conflicts(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError):
            _ = await env.di.scan_service.commit_adhoc(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_code=StockOperationCode.INTERNAL,
                context=ScanContext(flow=ScanFlow.MOVE),
                actor_user_id="test_user",
            )

    @pytest.mark.asyncio
    async def test_adhoc_ship_context_conflicts(
        self, stock_di, unique_id: str
    ) -> None:
        """``ship``/``container_move`` без строк — doc-driven потоки:
        adhoc из них не собирает документ (был бы пустой ghost-док)."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        contexts = (
            ScanContext(flow=ScanFlow.SHIP),
            ScanContext(
                flow=ScanFlow.CONTAINER_MOVE,
                container_id="ctr_1",
                dest_id="loc_1",
            ),
        )
        for ctx in contexts:
            with pytest.raises(PlatformConflictError):
                _ = await env.di.scan_service.commit_adhoc(
                    company_id=env.company_id,
                    warehouse_id=env.warehouse.warehouse_id,
                    operation_code=StockOperationCode.OUTGOING,
                    context=ctx,
                    actor_user_id="test_user",
                )

    @pytest.mark.asyncio
    async def test_adhoc_unknown_warehouse_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        """Склад не существует → типа операции нет → not found, ничего
        не проведено."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        ctx = ScanContext(
            flow=ScanFlow.MOVE,
            lines=(
                ScanLineDraft(
                    location_id="bin-a",
                    location_dest_id="bin-b",
                    product_id=env.product.product_id,
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.commit_adhoc(
                company_id=env.company_id,
                warehouse_id=f"wh-missing-{unique_id}",
                operation_code=StockOperationCode.INTERNAL,
                context=ctx,
                actor_user_id="test_user",
            )
        assert exc.value.error_code == "operation_type_not_found"

    @pytest.mark.asyncio
    async def test_adhoc_idempotent_retry(
        self, stock_di, unique_id: str
    ) -> None:
        """Повтор команды с тем же ключом — тот же документ, без
        второй проводки."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh = env.warehouse.warehouse_id
        ctx = ScanContext(
            flow=ScanFlow.RECEIVE,
            lines=(
                ScanLineDraft(
                    location_id=None,
                    location_dest_id=env.warehouse.stock_location_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("5"),
                ),
            ),
        )
        key = f"adhoc-{unique_id}"
        first = await env.di.scan_service.commit_adhoc(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_code=StockOperationCode.INCOMING,
            context=ctx,
            idempotency_key=key,
            actor_user_id="test_user",
        )
        second = await env.di.scan_service.commit_adhoc(
            company_id=env.company_id,
            warehouse_id=wh,
            operation_code=StockOperationCode.INCOMING,
            context=ctx,
            idempotency_key=key,
            actor_user_id="test_user",
        )
        assert second.transfer_id == first.transfer_id
        quant = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
        ).first()
        assert quant is not None
        assert quant.quantity == Decimal("5")

    @pytest.mark.asyncio
    async def test_adhoc_wrong_entity_kind_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """Контекст не в review-готовности (нет строк) отклоняется до
        создания документа — мусорных накладных не рождается."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        ctx = ScanContext(
            flow=ScanFlow.INQUIRY,
            lines=(
                ScanLineDraft(
                    location_id=None,
                    location_dest_id=None,
                    product_id=env.product.product_id,
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformConflictError):
            _ = await env.di.scan_service.commit_adhoc(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_code=StockOperationCode.INTERNAL,
                context=ctx,
                actor_user_id="test_user",
            )

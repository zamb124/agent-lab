"""Скан-движок ТСД — расширенные грани: машина, коммит, пересчёт.

Бизнес-правила под тестом дополнительно к базовой матрице потоков:

* машина не «молча принимает»: скан не на своём шаге отклоняется
  без порчи контекста, а review ждёт либо следующий товар, либо
  внешний commit — середину строки повторным сканом не переписать;
* коммит — деньги и остатки: «не тот товар» отклоняется
  (``scan_product_mismatch``), сверхрезервный факт пишется
  отдельной строкой и проводится только при реальном наличии,
  закрытые move скан не трогает;
* пересчёт (``count``) пишет черновик ``inventory_quantity`` —
  только на ячейках с физическим стоком: «посчитать» партнёра или
  зону-view создало бы фантомный quant;
* resolve — «что за код»: GTIN+serial → партия товара, фасовка
  несёт товар и кратность, ресурс для скан-потоков — UNKNOWN.
"""

from decimal import Decimal

import pytest

from apps.stock.models import (
    StockLocation,
    StockMove,
    StockMoveState,
    StockOperationCode,
    StockQuant,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    StockLayoutPreset,
    StockLocationUsage,
    StockPartnerRole,
    StockRemovalStrategy,
    StockTracking,
)
from apps.stock.models.move_line import StockMoveLine
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
from apps.stock.services.company_init_service import virtual_location_id
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)

from .test_stock_domain import StockEnv, _make_env, _receipt


def _res(
    kind: ScanEntityKind,
    entity_id: str | None,
    *,
    barcode: str = "",
    product_id: str | None = None,
    lot_id: str | None = None,
    serial: str | None = None,
    quantity: Decimal | None = None,
) -> ScanResolution:
    return ScanResolution(
        entity_kind=kind,
        entity_id=entity_id,
        barcode=barcode,
        product_id=product_id,
        lot_id=lot_id,
        serial=serial,
        quantity=quantity,
    )


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
    )


async def _reserved_move(env: StockEnv, qty: Decimal) -> StockMove:
    """Исходящая накладная confirm+assign → move с резервными строками."""
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
    _ = await env.di.move_engine.confirm_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    _ = await env.di.move_engine.assign_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    moves = await StockMove.list_for_transfer_by_created_at_asc(
        env.company_id, transfer.transfer_id
    )
    return moves[0]


class TestScanMachineEdges:
    """Чистая машина — отказы без порчи контекста."""

    def test_scan_after_done_rejected(self) -> None:
        ctx = ScanContext(
            flow=ScanFlow.CONTAINER_MOVE,
            step=ScanStep.DONE,
            container_id="c1",
            dest_id="d1",
        )
        r = scan_step(ctx, _res(ScanEntityKind.CONTAINER, "c2"))
        assert r.error == ScanError.UNEXPECTED_STEP
        assert r.context.container_id == "c1"  # контекст не тронут

    def test_review_rejects_non_product_scan(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "p1"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "b1"))
        r = scan_quantity(r.context, Decimal("1"))
        assert r.context.step == ScanStep.REVIEW
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "b2"))
        assert r.error == ScanError.UNEXPECTED_STEP
        assert r.context.step == ScanStep.REVIEW  # ждём commit/товар

    def test_entity_scan_on_quantity_step_rejected(self) -> None:
        ctx = ScanContext(flow=ScanFlow.RECEIVE)
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "p1"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "b1"))
        assert r.context.step == ScanStep.QUANTITY
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "b2"))
        assert r.error == ScanError.UNEXPECTED_STEP
        assert not r.context.lines

    def test_serial_scan_fills_serial_and_product(self) -> None:
        ctx = ScanContext(flow=ScanFlow.PICK)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(
            r.context,
            _res(
                ScanEntityKind.PRODUCT,
                "sn-1",
                product_id="prod-9",
                serial="SN-9",
            ),
        )
        assert r.error is None
        assert r.context.product_id == "prod-9"
        assert r.context.serial == "SN-9"

    def test_putaway_flow_sequence(self) -> None:
        """Putaway: товар → исходная тара/ячейка → приёмник → кол-во."""
        ctx = ScanContext(flow=ScanFlow.PUTAWAY)
        r = scan_step(ctx, _res(ScanEntityKind.PRODUCT, "p1"))
        assert r.context.step == ScanStep.LOCATION
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "dock"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-9"))
        r = scan_quantity(r.context, Decimal("2"))
        assert r.error is None
        line = r.context.lines[0]
        assert line.location_id == "dock"
        assert line.location_dest_id == "bin-9"

    def test_ship_flow_needs_only_source(self) -> None:
        ctx = ScanContext(flow=ScanFlow.SHIP)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "dock-1"))
        assert r.error is None and r.context.step == ScanStep.REVIEW
        # ship коммитит строки документа — своих строк не набирает.
        assert not r.context.lines
        assert scan_commit_ready(r.context) is None

    def test_move_dest_accepts_container(self) -> None:
        """Перенос «в короб»: приёмником может быть тара."""
        ctx = ScanContext(flow=ScanFlow.MOVE)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "p1"))
        r = scan_step(r.context, _res(ScanEntityKind.CONTAINER, "box-1"))
        assert r.context.step == ScanStep.QUANTITY
        r = scan_quantity(r.context, Decimal("1"))
        assert r.error is None
        assert r.context.lines[0].location_dest_id == "box-1"

    def test_count_requires_product(self) -> None:
        ctx = ScanContext(flow=ScanFlow.COUNT)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "p1"))
        r = scan_quantity(r.context, Decimal("0"))
        # Ноль — «не посчитано»: строка не снимается.
        assert r.error == ScanError.QUANTITY_REQUIRED

    def test_multiline_keeps_source_and_dest(self) -> None:
        """Переборка внутри зоны: ячейки не переспрашиваются
        на второй строке — слоты товара сброшены, концы у строк
        свои."""
        ctx = ScanContext(flow=ScanFlow.MOVE)
        r = scan_step(ctx, _res(ScanEntityKind.LOCATION, "bin-a"))
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "p1"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-b"))
        r = scan_quantity(r.context, Decimal("1"))
        r = scan_step(r.context, _res(ScanEntityKind.PRODUCT, "p2"))
        r = scan_step(r.context, _res(ScanEntityKind.LOCATION, "bin-c"))
        r = scan_quantity(r.context, Decimal("4"))
        assert len(r.context.lines) == 2
        assert r.context.lines[1].product_id == "p2"
        assert r.context.lines[1].location_dest_id == "bin-c"


class TestScanCommitEdges:
    """Коммит скан-сессии — границы и отказы на реальном Postgres."""

    async def test_empty_context_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ScanContext(flow=ScanFlow.PICK),
                actor_user_id="op",
            )
        assert exc.value.error_code == "scan_nothing_to_commit"

    async def test_commit_missing_move(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=None,
                    location_dest_id=None,
                    product_id="prod_any",
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id="mov_missing",
                context=ctx,
                actor_user_id="op",
            )
        assert exc.value.error_code == "move_not_found"

    async def test_commit_on_done_move_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        assert move.transfer_id is not None
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=move.transfer_id
        )
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ctx,
                actor_user_id="op",
            )
        assert exc.value.error_code == "move_state_conflict"

    async def test_wrong_product_scan_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """Отсканировали «не тот» товар — коммит не проводит чужое."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id="prod_other",
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ctx,
                actor_user_id="op",
            )
        assert exc.value.error_code == "scan_product_mismatch"

    async def test_over_scan_posts_excess_as_fact(
        self, stock_di, unique_id: str
    ) -> None:
        """Отсканировали больше резерва: сверх — строка
        quantity=0/done=факт (переотгрузка), остаток уходит полностью."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("2"))
        move = await _reserved_move(env, Decimal("4"))
        ctx = ScanContext(
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
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx,
            actor_user_id="op",
        )
        # Отгружено 6 вместо заказанных 4 — факт первичен.
        assert posted.state == StockMoveState.DONE
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quantity == Decimal("4")
        assert quant.reserved_quantity == Decimal("0")

    async def test_scan_more_than_physical_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Полки физически пусты: скан «воздуха» отклоняется —
        отрицательный остаток без allow_negative запрещён."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("3"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("5"),
                ),
            ),
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ctx,
                actor_user_id="op",
            )
        assert exc.value.error_code == "insufficient_stock"

    async def test_zero_and_negative_draft_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        for bad in (Decimal("0"), Decimal("-2")):
            ctx = ScanContext(
                flow=ScanFlow.PICK,
                lines=(
                    ScanLineDraft(
                        location_id=move.location_id,
                        location_dest_id=move.location_dest_id,
                        product_id=env.product.product_id,
                        quantity=bad,
                    ),
                ),
            )
            with pytest.raises(PlatformConflictError) as exc:
                _ = await env.di.scan_service.commit(
                    company_id=env.company_id,
                    move_id=move.move_id,
                    context=ctx,
                    actor_user_id="op",
                )
            assert exc.value.error_code == "done_quantity_invalid"

    async def test_commit_denied_on_foreign_claim(
        self, stock_di, unique_id: str
    ) -> None:
        """Строка захвачена оператором A — коммит оператора B
        отклоняется целиком: чужую работу исполнять нельзя
        («эти строки теперь мои» — контракт очереди)."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(
            env.company_id, move.move_id
        )
        _ = await env.di.task_service.claim(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[lines[0].move_line_id],
            user_id="op-A",
        )
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("3"),
                ),
            ),
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ctx,
                actor_user_id="op-B",
            )
        assert exc.value.error_code == "move_line_claimed"

        # Владелец claim исполняет свою строку без препятствий.
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx,
            actor_user_id="op-A",
        )
        assert posted.state == StockMoveState.DONE

    async def test_commit_replay_idempotent(
        self, stock_di, unique_id: str
    ) -> None:
        """Повтор команды по ключу — один и тот же результат,
        остаток не списывается дважды."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        ctx = ScanContext(
            flow=ScanFlow.PICK,
            lines=(
                ScanLineDraft(
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("2"),
                ),
            ),
        )
        key = f"scan-{unique_id}"
        first = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx,
            idempotency_key=key,
            actor_user_id="op",
        )
        second = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx,
            idempotency_key=key,
            actor_user_id="op",
        )
        assert second.state == first.state
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None and quant.quantity == Decimal("3")


class TestScanCountCommit:
    """Циклический пересчёт с ТСД: черновик → приказ → движение."""

    async def test_count_writes_draft_and_touches_location(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        stock = env.warehouse.stock_location_id
        ctx = ScanContext(
            flow=ScanFlow.COUNT,
            lines=(
                ScanLineDraft(
                    location_id=stock,
                    location_dest_id=None,
                    product_id=env.product.product_id,
                    quantity=Decimal("7"),
                ),
            ),
        )
        ids = await env.di.scan_service.inventory_count_commit(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            context=ctx,
            actor_user_id="counter",
        )
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=stock,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quant_id in ids
        assert quant.inventory_quantity == Decimal("7")
        # Книжный остаток черновиком не двигается.
        assert quant.quantity == Decimal("5")

    async def test_count_on_view_and_partner_denied(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        partner = virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER,
            StockPartnerRole.CUSTOMER,
        )
        for bad_loc in (env.warehouse.view_location_id, partner):
            ctx = ScanContext(
                flow=ScanFlow.COUNT,
                lines=(
                    ScanLineDraft(
                        location_id=bad_loc,
                        location_dest_id=None,
                        product_id=env.product.product_id,
                        quantity=Decimal("1"),
                    ),
                ),
            )
            with pytest.raises(PlatformConflictError) as exc:
                _ = await env.di.scan_service.inventory_count_commit(
                    company_id=env.company_id,
                    warehouse_id=env.warehouse.warehouse_id,
                    context=ctx,
                    actor_user_id="counter",
                )
            assert exc.value.error_code == "location_usage_invalid"

    async def test_count_on_missing_location(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        ctx = ScanContext(
            flow=ScanFlow.COUNT,
            lines=(
                ScanLineDraft(
                    location_id="loc_missing",
                    location_dest_id=None,
                    product_id=env.product.product_id,
                    quantity=Decimal("1"),
                ),
            ),
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.inventory_count_commit(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                context=ctx,
                actor_user_id="counter",
            )
        assert exc.value.error_code == "location_not_found"

    async def test_count_empty_context_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.inventory_count_commit(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                context=ScanContext(flow=ScanFlow.COUNT),
                actor_user_id="counter",
            )
        assert exc.value.error_code == "scan_nothing_to_commit"

    async def test_count_recount_overwrites_draft(
        self, stock_di, unique_id: str
    ) -> None:
        """Второй пересчёт той же ячейки переписывает черновик —
        последний факт первичен, до apply книга не меняется."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        stock = env.warehouse.stock_location_id
        for counted in (Decimal("4"), Decimal("6")):
            ctx = ScanContext(
                flow=ScanFlow.COUNT,
                lines=(
                    ScanLineDraft(
                        location_id=stock,
                        location_dest_id=None,
                        product_id=env.product.product_id,
                        quantity=counted,
                    ),
                ),
            )
            _ = await env.di.scan_service.inventory_count_commit(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                context=ctx,
                actor_user_id="counter",
            )
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=stock,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.inventory_quantity == Decimal("6")
        assert quant.quantity == Decimal("5")


class TestScanResolve:
    """«Что за код» — индекс + GS1 → тип сущности для машины."""

    async def test_product_barcode_resolves(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await env.di.stock_catalog_service.update_product(
            company_id=env.company_id,
            product_id=env.product.product_id,
            barcodes=[f"BC-{unique_id}"],
            is_active=None,
            valuation_method=None,
            standard_price=None,
            tracking=None,
        )
        res = await env.di.scan_service.resolve(
            company_id=env.company_id, barcode=f"BC-{unique_id}"
        )
        assert res.entity_kind == ScanEntityKind.PRODUCT
        assert res.entity_id == env.product.product_id

    async def test_product_multiple_barcodes_unique(
        self, stock_di, unique_id: str
    ) -> None:
        """У товара несколько кодов; каждый уникален между товарами."""
        env = await _env(stock_di, unique_id)
        view = await env.di.stock_catalog_service.update_product(
            company_id=env.company_id,
            product_id=env.product.product_id,
            barcodes=[f"BC1-{unique_id}", f"BC2-{unique_id}", f"BC3-{unique_id}"],
        )
        assert view.barcodes == [
            f"BC1-{unique_id}", f"BC2-{unique_id}", f"BC3-{unique_id}"
        ]
        for code in view.barcodes:
            res = await env.di.scan_service.resolve(
                company_id=env.company_id, barcode=code
            )
            assert res.entity_kind == ScanEntityKind.PRODUCT
            assert res.entity_id == env.product.product_id
        # Код чужого товара → barcode_conflict.
        other = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"Other {unique_id}",
            sku=f"OT-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.stock_catalog_service.update_product(
                company_id=env.company_id,
                product_id=other.product_id,
                barcodes=[f"BC2-{unique_id}"],
            )
        assert exc.value.error_code == "barcode_conflict"
        # PUT-форма: убранный код больше не резолвится.
        _ = await env.di.stock_catalog_service.update_product(
            company_id=env.company_id,
            product_id=env.product.product_id,
            barcodes=[f"BC3-{unique_id}"],
        )
        with pytest.raises(PlatformNotFoundError):
            _ = await env.di.scan_service.resolve(
                company_id=env.company_id, barcode=f"BC1-{unique_id}"
            )

    async def test_lot_barcode_carries_product(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        product = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"LT {unique_id}",
            sku=f"LT-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.LOT,
            is_storable=True,
            category="general",
        )
        lot = await env.di.stock_catalog_service.create_lot(
            company_id=env.company_id,
            product_id=product.product_id,
            name=f"LOT-{unique_id}",
            barcode=f"LB-{unique_id}",
            expiration_at=None,
        )
        res = await env.di.scan_service.resolve(
            company_id=env.company_id, barcode=f"LB-{unique_id}"
        )
        assert res.entity_kind == ScanEntityKind.LOT
        assert res.entity_id == lot.lot_id
        assert res.product_id == product.product_id

    async def test_serial_lot_barcode_fills_unit_quantity(
        self, stock_di, unique_id: str
    ) -> None:
        """Скан серийника — ровно одна штука: resolve подставляет
        quantity=1, «ввести 1» на каждом SN не требуется."""
        env = await _env(stock_di, unique_id)
        product = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"SN {unique_id}",
            sku=f"SN-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.SERIAL,
            is_storable=True,
            category="general",
        )
        lot = await env.di.stock_catalog_service.create_lot(
            company_id=env.company_id,
            product_id=product.product_id,
            name=f"SN-1-{unique_id}",
            barcode=f"SNB-{unique_id}",
            expiration_at=None,
        )
        res = await env.di.scan_service.resolve(
            company_id=env.company_id, barcode=f"SNB-{unique_id}"
        )
        assert res.entity_kind == ScanEntityKind.LOT
        assert res.lot_id == lot.lot_id
        assert res.quantity == Decimal("1")

    async def test_unknown_barcode_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.resolve(
                company_id=env.company_id, barcode=f"NOPE-{unique_id}"
            )
        assert exc.value.error_code == "barcode_not_found"

    async def test_resource_barcode_resolves_as_resource(
        self, stock_di, unique_id: str
    ) -> None:
        """Штрихкод техники резолвится как RESOURCE — ТСД показывает
        карточку ресурса; в активных потоках машина ответит ошибкой."""
        env = await _env(stock_di, unique_id)
        rtype = await env.di.topology_service.create_resource_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name=f"RT-{unique_id}",
            allowed_container_type_ids=[],
            storage_type_ids=[],
        )
        _ = await env.di.topology_service.create_resource(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_type_id=rtype.resource_type_id,
            code=f"RC-{unique_id}",
            barcode=f"RB-{unique_id}",
        )
        res = await env.di.scan_service.resolve(
            company_id=env.company_id, barcode=f"RB-{unique_id}"
        )
        assert res.entity_kind == ScanEntityKind.RESOURCE


class TestScanStepLocationGuard:
    """Слотившаяся ячейка — только реальная полка своего склада.

    Машина кладёт распознанную локацию в слот слепо; сервис сверху
    проверяет физику: ячейка активна, на quant-usage и — для ``bin`` —
    своего склада. Без этого скан ячейки чужого склада или зоны-
    группировки привёл бы остатки на место, где их физически нет.
    Контейнер складом не ограничен: тара ездит между складами.
    """

    @staticmethod
    def _receive_at_dest(env: StockEnv) -> ScanContext:
        return ScanContext(
            flow=ScanFlow.RECEIVE,
            step=ScanStep.DEST,
            product_id=env.product.product_id,
        )

    @pytest.mark.asyncio
    async def test_bin_of_other_warehouse_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Скан чужой ячейки на шаге DEST → scan_location_invalid,
        контекст не продвинулся — оператор узнаёт, что он не там."""
        env = await _env(stock_di, unique_id)
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WHX{unique_id[:6]}",
            name=f"Other {unique_id}",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        foreign_bin = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=other.warehouse_id,
            parent_id=other.view_location_id,
            name=f"FBIN-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        ctx = self._receive_at_dest(env)
        result = await env.di.scan_service.step(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            context=ctx,
            resolution=_res(ScanEntityKind.LOCATION, foreign_bin.location_id),
        )
        assert result.error == ScanError.LOCATION_INVALID
        assert result.context == ctx

    @pytest.mark.asyncio
    async def test_view_zone_as_dest_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Зона-view — логика навигации, остатков на ней нет: скан её
        кода как приёмника отклоняется, иначе товар «осел» бы на зоне."""
        env = await _env(stock_di, unique_id)
        ctx = self._receive_at_dest(env)
        result = await env.di.scan_service.step(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            context=ctx,
            resolution=_res(
                ScanEntityKind.LOCATION, env.warehouse.view_location_id
            ),
        )
        assert result.error == ScanError.LOCATION_INVALID
        assert result.context == ctx

    @pytest.mark.asyncio
    async def test_own_bin_passes(
        self, stock_di, unique_id: str
    ) -> None:
        """Своя активная ячейка — слотится и поток идёт к количеству."""
        env = await _env(stock_di, unique_id)
        own = await _bin(env, unique_id[:6])
        result = await env.di.scan_service.step(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            context=self._receive_at_dest(env),
            resolution=_res(ScanEntityKind.LOCATION, own.location_id),
        )
        assert result.error is None
        assert result.context.dest_id == own.location_id
        assert result.context.step == ScanStep.QUANTITY


async def _bin(env: StockEnv, suffix: str) -> StockLocation:
    return await env.di.topology_service.create_location(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        parent_id=env.warehouse.view_location_id,
        name=f"BIN-{suffix}",
        usage=StockLocationUsage.BIN,
        barcode=None,
    )


async def _loaded_location_id(env: StockEnv) -> str:
    """Ячейка, где физически лежит товар после прихода."""
    quants = await StockQuant.list_unordered_for_locations(
        env.company_id,
        await StockLocation.list_subtree_ids_by_parent_path_asc(
            env.company_id, env.warehouse.view_location_id
        ),
    )
    loaded = [
        q
        for q in quants
        if q.product_id == env.product.product_id
        and q.quantity > Decimal("0")
    ]
    assert loaded, "receipt did not stock the product"
    return loaded[0].location_id


async def _internal_move(
    env: StockEnv, dest_id: str, qty: Decimal
) -> StockMove:
    """INTERNAL transfer фактический источник → dest, confirm+assign."""
    src = await _loaded_location_id(env)
    internal = env.op_types[StockOperationCode.INTERNAL]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=internal.operation_type_id,
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
                location_id=src,
                location_dest_id=dest_id,
            )
        ],
    )
    for step in ("confirm", "assign"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    moves = await StockMove.list_for_transfer_by_created_at_asc(
        env.company_id, transfer.transfer_id
    )
    return moves[0]


async def _set_scan_flow(
    env: StockEnv, code: StockOperationCode, flow
) -> None:
    op = env.op_types[code]
    _ = await env.di.warehouse_service.update_operation_type(
        company_id=env.company_id,
        operation_type_id=op.operation_type_id,
        name=None,
        reservation_policy=None,
        backorder_policy=None,
        putaway_mode=None,
        putaway_flow_id=None,
        auto_validate=None,
        scan_flow=flow,
    )


class TestScanLegFlows:
    """Плечи маршрута pack/ship — явная семантика типа операции.

    ``scan_flow`` на типе операции побеждает вывод из ``code``: один
    класс накладной обслуживает и сборку (pick), и упаковку (pack),
    и отгрузку (ship) — какое плечо исполняет ТСД, решает настройка
    компании, а не захардкоженный порядок экранов.
    """

    async def test_open_session_ship_flow_for_ship_op_type(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        await _set_scan_flow(env, StockOperationCode.OUTGOING, ScanFlow.SHIP)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=move.move_id,
            transfer_id=None,
            user_id="op",
        )
        assert ctx.flow == ScanFlow.SHIP

    async def test_open_session_pack_flow_for_pack_op_type(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        await _set_scan_flow(env, StockOperationCode.INTERNAL, ScanFlow.PACK)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        dest = await _bin(env, f"P{unique_id[:6]}")
        move = await _internal_move(env, dest.location_id, Decimal("2"))
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=move.move_id,
            transfer_id=None,
            user_id="op",
        )
        assert ctx.flow == ScanFlow.PACK

    async def test_open_session_pick_flow_without_override(
        self, stock_di, unique_id: str
    ) -> None:
        """Без явной настройки исходящая остаётся сборкой — вывод из code."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=move.move_id,
            transfer_id=None,
            user_id="op",
        )
        assert ctx.flow == ScanFlow.PICK

    async def test_scan_flow_default_clears_override(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        await _set_scan_flow(env, StockOperationCode.OUTGOING, ScanFlow.SHIP)
        await _set_scan_flow(env, StockOperationCode.OUTGOING, "default")
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=move.move_id,
            transfer_id=None,
            user_id="op",
        )
        assert ctx.flow == ScanFlow.PICK

    async def test_ship_commit_posts_all_open_lines(
        self, stock_di, unique_id: str
    ) -> None:
        """Ship-плечо: «док уехал» — весь резерв документа проводится
        одной кнопкой, без пересканирования каждой позиции."""
        env = await _env(stock_di, unique_id)
        await _set_scan_flow(env, StockOperationCode.OUTGOING, ScanFlow.SHIP)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ScanContext(flow=ScanFlow.SHIP),
            actor_user_id="op",
        )
        assert posted.state == StockMoveState.DONE
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Пришло 5, отгружено резервом 3 — остаток источника 2.
        assert quant is not None and quant.quantity == Decimal("2")

    async def test_ship_denied_for_plain_outgoing(
        self, stock_di, unique_id: str
    ) -> None:
        """Контекст приходит с клиента — «ship» для обычной сборки
        отклоняется, проверка по типу операции, не по заявлению."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ScanContext(flow=ScanFlow.SHIP),
                actor_user_id="op",
            )
        assert exc.value.error_code == "scan_ship_denied"

    async def test_dest_override_consumes_reserve(
        self, stock_di, unique_id: str
    ) -> None:
        """Документ обещал ячейку A, оператор положил в ячейку B:
        резерв гасится по источнику и товару, факт пишется с реальным
        приёмником — move закрывается, висячего резерва нет."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        promised = await _bin(env, f"A{unique_id[:6]}")
        actual = await _bin(env, f"B{unique_id[:6]}")
        move = await _internal_move(
            env, promised.location_id, Decimal("2")
        )
        ctx = ScanContext(
            flow=ScanFlow.MOVE,
            lines=(
                ScanLineDraft(
                    location_id=None,
                    location_dest_id=actual.location_id,
                    product_id=env.product.product_id,
                    quantity=Decimal("2"),
                ),
            ),
        )
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ctx,
            actor_user_id="op",
        )
        assert posted.state == StockMoveState.DONE
        fact = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=actual.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert fact is not None and fact.quantity == Decimal("2")
        promised_quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=promised.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert promised_quant is None or promised_quant.quantity == Decimal(
            "0"
        )

    async def test_open_session_denied_when_fully_claimed(
        self, stock_di, unique_id: str
    ) -> None:
        """Все открытые строки захвачены другим — документ для этого
        оператора пуст: открытие сессии честно отвечает «нет работы»."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(
            env.company_id, move.move_id
        )
        _ = await env.di.task_service.claim(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line.move_line_id for line in lines],
            user_id="op-A",
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.open_session(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_id=move.move_id,
                transfer_id=None,
                user_id="op-B",
            )
        assert exc.value.error_code == "document_no_work"
        # Владелец открывает свой документ без препятствий.
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=move.move_id,
            transfer_id=None,
            user_id="op-A",
        )
        assert ctx.flow == ScanFlow.PICK


class TestExpectedHint:
    """Подсказка экрану и инвариант open-строки.

    ``done_quantity`` открытой строки — подсказка кладовщику
    («сколько взять»), ``quantity`` — держимый резерв. Частичный
    скан-коммит урезает ОБЕ — иначе последующий ship-плечо провело
    бы уже отсканированное второй раз (переотгрузка фактом).
    """

    async def test_first_executable_line_done_is_hint(
        self, stock_di, unique_id: str
    ) -> None:
        """Подсказка «сколько взять» читается из ``done_quantity``
        первой исполнимой строки — полного остатка задания."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("8"), Decimal("2"))
        move = await _reserved_move(env, Decimal("5"))
        line = await env.di.scan_service.first_executable_line(
            company_id=env.company_id,
            move_id=move.move_id,
            user_id="op",
        )
        assert line is not None
        assert line.quantity == Decimal("5")
        assert line.done_quantity == Decimal("5")

    async def test_partial_scan_commit_then_ship_posts_remainder(
        self, stock_di, unique_id: str
    ) -> None:
        """Частичный отбор сканом урезает done вместе с резервом:
        ship-плечо проводит только остаток задания, а не исходную
        массу строки — иначе уехало бы больше, чем заказано."""
        env = await _env(stock_di, unique_id)
        await _set_scan_flow(env, StockOperationCode.OUTGOING, ScanFlow.SHIP)
        _ = await _receipt(env, Decimal("8"), Decimal("2"))
        move = await _reserved_move(env, Decimal("5"))
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ScanContext(
                flow=ScanFlow.PICK,
                lines=(
                    ScanLineDraft(
                        location_id=move.location_id,
                        location_dest_id=move.location_dest_id,
                        product_id=env.product.product_id,
                        quantity=Decimal("2"),
                    ),
                ),
            ),
            actor_user_id="op",
        )
        assert posted.state != StockMoveState.DONE
        open_lines = await StockMoveLine.list_open_for_move_by_created_at_asc(
            env.company_id, move.move_id
        )
        assert len(open_lines) == 1
        assert open_lines[0].quantity == Decimal("3")
        assert open_lines[0].done_quantity == Decimal("3")
        posted = await env.di.scan_service.commit(
            company_id=env.company_id,
            move_id=move.move_id,
            context=ScanContext(flow=ScanFlow.SHIP),
            actor_user_id="op",
        )
        assert posted.state == StockMoveState.DONE
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Отгружено ровно 5 (2 сканом + 3 доком), на источнике 3.
        assert quant is not None and quant.quantity == Decimal("3")


class TestScanOpenByLine:
    """Открытие сессии по конкретному заданию — kind строки диктует поток.

    Движение со смешанными строками (отбор + задание пересчёта той же
    ячейки после исключения) обязано открыть поток именно той работы,
    за которую взялся оператор: тап по «пересчитать» — count-экран,
    тап по «собрать» — pick-экран, а не поток первой попавшейся строки.
    """

    async def test_open_session_by_count_line_opens_count_flow(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(
                env.company_id, move.move_id
            )
        )[0]
        exc = await env.di.task_service.report_exception(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_id=line.move_line_id,
            shortage=Decimal("1"),
            reason="not_on_shelf",
            actor_user_id="op",
        )
        # Тап по заданию пересчёта → count-сессия, хотя на том же
        # движении висит и отборочная строка.
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=None,
            transfer_id=None,
            user_id="op",
            move_line_id=exc.count_line_id,
        )
        assert ctx.flow == ScanFlow.COUNT

    async def test_open_session_by_quantity_line_stays_pick(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(
                env.company_id, move.move_id
            )
        )[0]
        _ = await env.di.task_service.report_exception(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_id=line.move_line_id,
            shortage=Decimal("1"),
            reason="not_on_shelf",
            actor_user_id="op",
        )
        _, ctx = await env.di.scan_service.open_session(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_id=move.move_id,
            transfer_id=None,
            user_id="op",
            move_line_id=line.move_line_id,
        )
        assert ctx.flow == ScanFlow.PICK

    async def test_open_session_by_other_claimed_line_denied(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(
                env.company_id, move.move_id
            )
        )[0]
        _ = await env.di.task_service.claim(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line.move_line_id],
            user_id="op-A",
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.scan_service.open_session(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_id=move.move_id,
                transfer_id=None,
                user_id="op-B",
                move_line_id=line.move_line_id,
            )
        assert exc.value.error_code == "move_line_claimed"

    async def test_first_executable_line_scoped_by_kind(
        self, stock_di, unique_id: str
    ) -> None:
        """Подсказка count-сессии показывает count-строку, а не отбор."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        line = (
            await StockMoveLine.list_open_for_move_by_created_at_asc(
                env.company_id, move.move_id
            )
        )[0]
        exc = await env.di.task_service.report_exception(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_id=line.move_line_id,
            shortage=Decimal("1"),
            reason="not_on_shelf",
            actor_user_id="op",
        )
        count_kind = env.di.scan_service.kinds_of_flow(ScanFlow.COUNT)
        first = await env.di.scan_service.first_executable_line(
            company_id=env.company_id,
            move_id=move.move_id,
            user_id="op",
            kinds=count_kind,
        )
        assert first is not None
        assert first.move_line_id == exc.count_line_id
        qty_kind = env.di.scan_service.kinds_of_flow(ScanFlow.PICK)
        first = await env.di.scan_service.first_executable_line(
            company_id=env.company_id,
            move_id=move.move_id,
            user_id="op",
            kinds=qty_kind,
        )
        assert first is not None
        assert first.move_line_id == line.move_line_id

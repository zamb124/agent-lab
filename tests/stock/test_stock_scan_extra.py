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
    StockMove,
    StockMoveState,
    StockOperationCode,
    StockQuant,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    StockLocationUsage,
    StockPartnerRole,
    StockTracking,
)
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
                ScanEntityKind.SERIAL,
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
        assert quant.quantity == Decimal("3")


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

    async def test_unknown_barcode_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.scan_service.resolve(
                company_id=env.company_id, barcode=f"NOPE-{unique_id}"
            )
        assert exc.value.error_code == "barcode_not_found"

    async def test_resource_barcode_is_unknown_for_flows(
        self, stock_di, unique_id: str
    ) -> None:
        """Штрихкод техники распознаётся индексом, но скан-потокам
        он бесполезен → UNKNOWN (машина ответит not_found)."""
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
        assert res.entity_kind == ScanEntityKind.UNKNOWN

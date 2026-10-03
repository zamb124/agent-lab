"""Инвентаризация — сверка книжного остатка с физическим.

Бизнес-правила под тестом:

* подсчёт двухфазный: ``inventory_set`` фиксирует «насчитали N»,
  ``inventory_apply`` превращает расхождение в проведённый StockMove
  через виртуальную локацию ``adjustment`` — движение не «правка
  цифры», а документ с записью в журнале стоимости;
* недостача → ``bin → adjustment`` (INVENTORY_LOSS: минус со склада
  и из оценки по себестоимости метода карточки);
* излишек → ``adjustment → bin`` (INVENTORY_GAIN по карточной цене);
* черновик подсчёта сгорает при apply — повторный apply без нового
  подсчёта невозможен (``inventory_empty``), ноль дельты —
  ``inventory_delta_zero``;
* подсчёт партионного quant'а двигает строго его партию — соседняя
  партия на той же ячейке не затрагивается;
* подсчёт не снимает резерв: книжное ``reserved_quantity`` остаётся
  обещанием других документов (физика может уйти ниже резерва —
  это сигнал расхождения, а не автосписание чужого обещания).
"""

from decimal import Decimal

import pytest

from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    StockMoveState,
    StockOperationCode,
    StockTracking,
    ValuationMethod,
    ValueEntryKind,
)
from apps.stock.models.quant import StockQuant
from core.errors.boundary import PlatformConflictError

from .test_stock_domain import (
    StockEnv,
    _layers,
    _make_env,
    _receipt,
    _stock_quant,
)
from .test_stock_tracking import _lot, _receipt_lot, _tracked_product


async def _env(
    stock_di, unique_id: str, valuation=ValuationMethod.FIFO
) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, valuation
    )


async def _count(
    env: StockEnv, quant: StockQuant, counted: Decimal
) -> None:
    _ = await env.di.move_engine.inventory_set(
        company_id=env.company_id,
        quant_id=quant.quant_id,
        inventory_quantity=counted,
    )


class TestLoss:
    async def test_shortage_writes_loss_layer_and_moves_quant(
        self, stock_di, unique_id: str
    ) -> None:
        """Было 5, насчитали 3: −2 шт списываются в adjustment,
        журнал получает INVENTORY_LOSS по себестоимости."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        quant = await _stock_quant(env)
        await _count(env, quant, Decimal("3"))
        move = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )
        assert move.location_id == quant.location_id
        fresh = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert fresh.quantity == Decimal("3")
        loss = next(
            layer for layer in await _layers(env)
            if layer.entry_kind == ValueEntryKind.INVENTORY_LOSS
        )
        assert loss.quantity == Decimal("-2")
        assert loss.value == Decimal("-8")
        assert loss.qty_after == Decimal("3")
        assert loss.value_after == Decimal("12")


class TestDraftLifecycle:
    async def test_second_apply_without_count_fails(
        self, stock_di, unique_id: str
    ) -> None:
        """Черновик сгорает на apply — повторить проводку без
        нового подсчёта нельзя (иначе дельта спишется дважды)."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        quant = await _stock_quant(env)
        await _count(env, quant, Decimal("3"))
        _ = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.move_engine.inventory_apply(
                company_id=env.company_id, quant_id=quant.quant_id
            )
        assert exc.value.error_code == "inventory_empty"

    async def test_set_overwrites_previous_draft(
        self, stock_di, unique_id: str
    ) -> None:
        """Пересчёт до утверждения заменяет черновик —
        проводится последняя цифра, а не сумма попыток."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        quant = await _stock_quant(env)
        await _count(env, quant, Decimal("3"))
        await _count(env, quant, Decimal("7"))
        _ = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )
        fresh = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert fresh.quantity == Decimal("7")
        gain = next(
            layer for layer in await _layers(env)
            if layer.entry_kind == ValueEntryKind.INVENTORY_GAIN
        )
        assert gain.quantity == Decimal("2")

    async def test_apply_returns_done_move_with_inventory_origin(
        self, stock_di, unique_id: str
    ) -> None:
        """Приказ об инвентаризации — это и есть документ:
        move сразу done и ссылается на quant как на основание."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        quant = await _stock_quant(env)
        await _count(env, quant, Decimal("4"))
        move = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )
        assert move.state == StockMoveState.DONE
        assert move.origin_document_type == "stock_inventory"
        assert move.origin_document_id == quant.quant_id


class TestLotInventory:
    async def test_count_adjusts_only_its_lot(
        self, stock_di, unique_id: str
    ) -> None:
        """Инвентаризация адресная до партии: недостача LOT-A
        не трогает остаток LOT-B на той же ячейке."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"invl-{unique_id}", StockTracking.LOT
        )
        lot_a = await _lot(env, product.product_id, f"A-{unique_id}")
        lot_b = await _lot(env, product.product_id, f"B-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("2"), lot_a.lot_id)
        _ = await _receipt_lot(env, product.product_id, Decimal("3"), lot_b.lot_id)
        qa = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_a.lot_id,
            owner_entity_id=None,
        )
        await _count(env, qa, Decimal("1"))
        _ = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=qa.quant_id
        )
        qa = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_a.lot_id,
            owner_entity_id=None,
        )
        qb = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_b.lot_id,
            owner_entity_id=None,
        )
        assert qa.quantity == Decimal("1")
        assert qb.quantity == Decimal("3")


class TestReservedInventory:
    async def test_count_below_reservation_keeps_promise(
        self, stock_di, unique_id: str
    ) -> None:
        """Подсчёт меньше резерва: физика падает, обещание
        остаётся — резерв не снимается «втихую» инвентаризацией."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
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
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        quant = await _stock_quant(env)
        assert quant.reserved_quantity == Decimal("4")
        await _count(env, quant, Decimal("3"))
        _ = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )
        fresh = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Физики 3, обещано 4 — расхождение видно, резерв не потёрт.
        assert fresh.quantity == Decimal("3")
        assert fresh.reserved_quantity == Decimal("4")

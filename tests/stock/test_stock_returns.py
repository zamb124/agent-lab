"""Возвраты — обратные накладные и денежный откат.

Бизнес-правила под тестом:

* возврат — новый transfer с ``return_of_id``, строки зеркальны
  (источник/приёмник перевернуты), оригинал не трогается;
* вернуть можно не больше, чем РЕАЛЬНО доставлено по строке
  (``delivered − already_returned``): запрос сверх остатка —
  ``return_quantity_exceeded``, серия частичных возвратов суммарно
  не может превысить факт отгрузки;
* возврат проводится сразу (факт, а не заявка) и оценивается по
  себестоимости исходной проводки — деньги «откатываются» ровно на
  ту сумму, на которую товар ушёл/пришёл;
* трассируемый товар возвращается той же партией/серийником, что
  ушёл — иначе на складе появится безликий остаток.
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
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.quant import StockQuant
from core.errors.boundary import (
    PlatformConflictError,
)

from .test_stock_domain import (
    StockEnv,
    _delivery,
    _layers,
    _make_env,
    _receipt,
    _stock_quant,
)


async def _env(stock_di, unique_id: str, valuation=ValuationMethod.FIFO):
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, valuation
    )


async def _moves(env: StockEnv, transfer_id: str) -> list[StockMove]:
    return await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer_id)


async def _delivered_move(env: StockEnv, transfer_id: str) -> StockMove:
    moves = await _moves(env, transfer_id)
    return moves[0]


async def _partial_delivery(
    env: StockEnv, ordered: Decimal, done: Decimal
) -> str:
    """Исходящая накладная, проведённая частично: ordered > done.

    Остаток уходит в backorder (политика типа операции ``always``).
    """
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
                product_qty=ordered,
                uom_id=env.uom_id,
            )
        ],
    )
    for step in ("confirm", "assign"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    line = (
        await StockMoveLine.list_for_moves_by_created_at_asc(
            env.company_id,
            [m.move_id for m in await _moves(env, transfer.transfer_id)],
        )
    )[0]
    _ = await env.di.task_service.update_move_line(
        company_id=env.company_id,
        move_line_id=line.move_line_id,
        done_quantity=done,
        picked=None,
        lot_id=None,
        location_dest_id=None,
    )
    _ = await env.di.move_engine.validate_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    return transfer.transfer_id


class TestReturnHappyPath:
    async def test_full_return_restores_stock(
        self, stock_di, unique_id: str
    ) -> None:
        """Полный возврат отгрузки: остаток восстановлен один в один,
        в журнале — запись RETURN, откатывающая деньги на ту же сумму."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        assert ret.return_of_id == delivery_id
        assert "/RET/" in ret.name
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("10")
        layers = await _layers(env)
        ret_layer = next(
            layer for layer in layers if layer.entry_kind == ValueEntryKind.RETURN
        )
        # Отгрузка съела 4 шт по себестоимости 4 ₽ → возврат +16 ₽.
        assert ret_layer.quantity == Decimal("4")
        assert ret_layer.value == Decimal("16")
        last = layers[-1]
        assert last.qty_after == Decimal("10")
        assert last.value_after == Decimal("40")

    async def test_return_moves_are_reversed_and_linked(
        self, stock_di, unique_id: str
    ) -> None:
        """Возвратный move — зеркало оригинала: концы перевернуты,
        ``returned_move_id`` ссылается на исходную строку."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("5"))
        delivery_id = await _delivery(env, Decimal("3"))
        origin = await _delivered_move(env, delivery_id)
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        ret_moves = await _moves(env, ret.transfer_id)
        assert len(ret_moves) == 1
        rm = ret_moves[0]
        assert rm.returned_move_id == origin.move_id
        assert rm.location_id == origin.location_dest_id
        assert rm.location_dest_id == origin.location_id
        assert rm.product_qty == Decimal("3")
        assert rm.state == StockMoveState.DONE
        # Оригинал не тронут — документ остаётся done.
        origin_fresh = await StockMove.by_id(
            env.company_id, origin.move_id
        )
        assert origin_fresh is not None
        assert origin_fresh.state == StockMoveState.DONE

    async def test_partial_return_quantities(
        self, stock_di, unique_id: str
    ) -> None:
        """Вернули 2 из 4: остаток растёт ровно на 2, второй возврат
        по остатку — на 2, третий уже упирается в потолок."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        move = await _delivered_move(env, delivery_id)

        first = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities={move.move_id: Decimal("2")},
        )
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("8")
        ret_move = (await _moves(env, first.transfer_id))[0]
        assert ret_move.product_qty == Decimal("2")

        second = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities={move.move_id: Decimal("2")},
        )
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("10")
        ret_move2 = (await _moves(env, second.transfer_id))[0]
        assert ret_move2.product_qty == Decimal("2")


class TestReturnGuards:
    async def test_over_return_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """«Вернуть 7 из отгруженных 4» — просьба напечатать товар
        из воздуха. Код — ``return_quantity_exceeded``."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        move = await _delivered_move(env, delivery_id)
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.move_engine.return_transfer(
                company_id=env.company_id,
                transfer_id=delivery_id,
                move_quantities={move.move_id: Decimal("7")},
            )
        assert exc.value.error_code == "return_quantity_exceeded"
        # Остаток не шелохнулся — отказ до записи.
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("6")

    async def test_cumulative_return_cap(
        self, stock_di, unique_id: str
    ) -> None:
        """Серия частичных возвратов: 2 + 2 по строке «ушло 4» —
        ок; попытка вернуть ещё 1 сверх полного отката — отказ."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        move = await _delivered_move(env, delivery_id)
        for q in (Decimal("2"), Decimal("2")):
            _ = await env.di.move_engine.return_transfer(
                company_id=env.company_id,
                transfer_id=delivery_id,
                move_quantities={move.move_id: q},
            )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.move_engine.return_transfer(
                company_id=env.company_id,
                transfer_id=delivery_id,
                move_quantities={move.move_id: Decimal("1")},
            )
        assert exc.value.error_code == "return_quantity_exceeded"

    async def test_default_qty_caps_at_delivered(
        self, stock_di, unique_id: str
    ) -> None:
        """Частичная проводка: заказ 5, исполнено 3 → возврат «всё»
        возвращает 3, а не заказанные 5."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _partial_delivery(
            env, ordered=Decimal("5"), done=Decimal("3")
        )
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        ret_move = (await _moves(env, ret.transfer_id))[0]
        assert ret_move.product_qty == Decimal("3")
        quant = await _stock_quant(env)
        assert quant is not None
        # 10 − 3 (отгрузка) + 3 (возврат) = 10.
        assert quant.quantity == Decimal("10")

    async def test_zero_qty_lines_skipped(
        self, stock_di, unique_id: str
    ) -> None:
        """move_quantities с нулём по строке — строка не возвращается,
        пустая возвратная накладная не рождает движений."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        move = await _delivered_move(env, delivery_id)
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities={move.move_id: Decimal("0")},
        )
        ret_moves = await _moves(env, ret.transfer_id)
        assert ret_moves == []
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("6")

    async def test_unknown_move_id_in_map_skipped(
        self, stock_di, unique_id: str
    ) -> None:
        """Ключи move_quantities, не принадлежащие документу,
        не создают возвратных строк — только явные move."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities={"mov-foreign": Decimal("2")},
        )
        ret_moves = await _moves(env, ret.transfer_id)
        assert ret_moves == []
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("6")

    async def test_double_return_via_same_key_is_replay(
        self, stock_di, unique_id: str
    ) -> None:
        """Повторная команда возврата с тем же idempotency_key —
        replay записи полосы, а не второй возврат."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("4"))
        ret1 = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
            idempotency_key=f"ret-{unique_id}",
        )
        ret2 = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
            idempotency_key=f"ret-{unique_id}",
        )
        assert ret2.transfer_id == ret1.transfer_id
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("10")


class TestReturnValuation:
    """Деньги возврата: оценка по себестоимости исходного move,
    не по карточке и не по цене продажи."""

    async def test_return_uses_origin_cost_not_card(
        self, stock_di, unique_id: str
    ) -> None:
        """STANDARD-карточка 100 ₽, приход был по 4 ₽ → возврат
        идёт по 4 ₽ (себестоимость исходной проводки)."""
        env = await _env(stock_di, unique_id, ValuationMethod.STANDARD)
        _ = await env.di.catalog_service.update_product(
            company_id=env.company_id,
            product_id=env.product.product_id,
            name=None,
            sku=None,
            barcode=None,
            is_active=None,
            valuation_method=None,
            standard_price=Decimal("100"),
            tracking=None,
        )
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        delivery_id = await _delivery(env, Decimal("2"))
        _ = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        layers = await _layers(env)
        ret = next(
            layer for layer in layers if layer.entry_kind == ValueEntryKind.RETURN
        )
        # Возврат по себестоимости исходного OUTBOUND (standard=100),
        # не по цене прихода: OUTBOUND слой списал по standard_price.
        assert ret.unit_cost == Decimal("100")
        assert ret.value == Decimal("200")

    async def test_fifo_return_restores_consumed_layer_value(
        self, stock_di, unique_id: str
    ) -> None:
        """FIFO: два прихода по разным ценам → отгрузка съела старый
        слой → возврат приносит обратно именно его себестоимость."""
        env = await _env(stock_di, unique_id, ValuationMethod.FIFO)
        _ = await _receipt(env, Decimal("2"), Decimal("3"))
        _ = await _receipt(env, Decimal("2"), Decimal("7"))
        delivery_id = await _delivery(env, Decimal("2"))
        _ = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        layers = await _layers(env)
        ret_layer = next(
            layer for layer in layers if layer.entry_kind == ValueEntryKind.RETURN
        )
        # Отгрузка съела слой по 3 ₽ (FIFO), возврат возвращает те же 3 ₽.
        assert ret_layer.unit_cost == Decimal("3")
        assert ret_layer.value == Decimal("6")
        last = layers[-1]
        assert last.qty_after == Decimal("4")
        assert last.value_after == Decimal("20")


class TestReturnTracking:
    """Возврат трассируемого товара — той же партией/серийником."""

    async def _tracked_env(self, stock_di, unique_id, tracking):
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        env.product = await stock_di.catalog_service.create_product(
            company_id=env.company_id,
            name=f"Tracked {unique_id}",
            sku=f"TRK-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=tracking,
            is_storable=True,
            category="general",
            barcode=None,
        )
        return env

    async def _receipt_with_lot(
        self, env: StockEnv, qty: Decimal, lot_name: str
    ) -> str:
        op = env.op_types[StockOperationCode.INCOMING]
        lot = await env.di.catalog_service.create_lot(
            company_id=env.company_id,
            product_id=env.product.product_id,
            name=lot_name,
            barcode=None,
            expiration_at=None,
        )
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
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        line = (
            await StockMoveLine.list_for_moves_by_created_at_asc(
                env.company_id,
                [
                    m.move_id
                    for m in await _moves(env, transfer.transfer_id)
                ],
            )
        )[0]
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=line.move_line_id,
            done_quantity=None,
            picked=None,
            lot_id=lot.lot_id,
            location_dest_id=None,
        )
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        return transfer.transfer_id

    async def test_lot_return_keeps_trace(
        self, stock_di, unique_id: str
    ) -> None:
        """Возврат партии: остаток поднимается на ТОЙ ЖЕ партии —
        иначе серия/качество потеряют след."""
        env = await self._tracked_env(
            stock_di, unique_id, StockTracking.LOT
        )
        _ = await self._receipt_with_lot(env, Decimal("5"), "LOT-A")
        delivery_id = await _delivery(env, Decimal("2"))
        # Отгрузка резервирует quant с партией — line.lot_id выставлен.
        origin_move = await _delivered_move(env, delivery_id)
        origin_lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, origin_move.move_id
        )
        assert origin_lines[0].lot_id is not None
        lot_id = origin_lines[0].lot_id

        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        ret_moves = await _moves(env, ret.transfer_id)
        ret_lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, ret_moves[0].move_id
        )
        assert ret_lines[0].lot_id == lot_id
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_id,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quantity == Decimal("5")

    async def test_serial_return_keeps_trace(
        self, stock_di, unique_id: str
    ) -> None:
        """Серийник возвращается тем же номером — уникальность
        «один SN = одна единица» сохраняется после отката."""
        env = await self._tracked_env(
            stock_di, unique_id, StockTracking.SERIAL
        )
        _ = await self._receipt_with_lot(env, Decimal("1"), "SN-1")
        delivery_id = await _delivery(env, Decimal("1"))
        origin_move = await _delivered_move(env, delivery_id)
        origin_lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, origin_move.move_id
        )
        sn = origin_lines[0].lot_id
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        ret_moves = await _moves(env, ret.transfer_id)
        ret_lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, ret_moves[0].move_id
        )
        assert ret_lines[0].lot_id == sn
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=sn,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quantity == Decimal("1")

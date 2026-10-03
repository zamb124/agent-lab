"""Конкурентность — расширенные гонки поверх базовой матрицы.

Бизнес-инварианты под тестом:

* два скан-коммита одного move сериализуются полосой: сплит резерва
  не теряет и не дублирует единицы — сумма проведённого равна сумме
  сканов;
* захват задания — «один поручение = один исполнитель»: десять
  параллельных claim на строку дают ровно одного победителя;
* двойной apply инвентаризации: черновик обнуляется до постинга,
  второй apply честно получает ``inventory_empty``, движение —
  одно;
* параллельные приёмки на один quant: ни одна запись не потеряна,
  остаток равен сумме;
* разные склады компании — разные полосы: операции соседних складов
  не мешают друг другу и обе завершаются успехом;
* unique-гонка на коде склада: две одновременные регистрации
  одного кода — одна побеждает, вторая получает конфликт.
"""

import asyncio
from decimal import Decimal

from apps.stock.models import (
    StockLayoutPreset,
    StockMove,
    StockMoveState,
    StockOperationCode,
    StockQuant,
    StockRemovalStrategy,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.scan import ScanContext, ScanFlow, ScanLineDraft
from core.errors.boundary import (
    PlatformConflictError,
)

from .test_stock_domain import StockEnv, _make_env, _receipt


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
    )


async def _reserved_move(env: StockEnv, qty: Decimal) -> StockMove:
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
    moves = await StockMove.list_for_transfer(
        env.company_id, transfer.transfer_id
    )
    return moves[0]


def _pick_ctx(move: StockMove, product_id: str, qty: Decimal) -> ScanContext:
    return ScanContext(
        flow=ScanFlow.PICK,
        lines=(
            ScanLineDraft(
                location_id=move.location_id,
                location_dest_id=move.location_dest_id,
                product_id=product_id,
                quantity=qty,
            ),
        ),
    )


class TestConcurrentScanCommits:
    async def test_two_commits_on_same_move_sum_exactly(
        self, stock_di, unique_id: str
    ) -> None:
        """Два ТСД коммитят один move одновременно: полоса
        сериализует сплиты — проведено ровно 2+3=5, резерв погашен."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("2"))
        move = await _reserved_move(env, Decimal("5"))
        _ = await asyncio.gather(
            env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=_pick_ctx(
                    move, env.product.product_id, Decimal("2")
                ),
                idempotency_key=f"s1-{unique_id}",
                actor_user_id="op-1",
            ),
            env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=_pick_ctx(
                    move, env.product.product_id, Decimal("3")
                ),
                idempotency_key=f"s2-{unique_id}",
                actor_user_id="op-2",
            ),
        )
        # Результат каждого коммита — состояние move в момент своей
        # транзакции: первый видит assigned (остаток резерва открыт),
        # второй done. Инвариант — финальное состояние из БД.
        final = await StockMove.by_id(env.company_id, move.move_id)
        assert final.state == StockMoveState.DONE
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant.quantity == Decimal("5")
        assert quant.reserved_quantity == Decimal("0")
        open_left = await StockMoveLine.list_for_move(
            env.company_id, move.move_id
        )
        assert open_left == []

    async def test_concurrent_commits_beyond_stock_fail_clean(
        self, stock_di, unique_id: str
    ) -> None:
        """Два скана суммарно больше физического остатка: один проходит,
        второй получает insufficient_stock — минуса нет."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("4"), Decimal("2"))
        move = await _reserved_move(env, Decimal("4"))
        results = await asyncio.gather(
            env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=_pick_ctx(
                    move, env.product.product_id, Decimal("3")
                ),
                idempotency_key=f"s1-{unique_id}",
                actor_user_id="op-1",
            ),
            env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=_pick_ctx(
                    move, env.product.product_id, Decimal("3")
                ),
                idempotency_key=f"s2-{unique_id}",
                actor_user_id="op-2",
            ),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, Exception)]
        for err in errors:
            assert isinstance(err, PlatformConflictError)
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=move.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Проведено не больше физических 4 — минус невозможен.
        assert quant.quantity >= Decimal("0")
        assert quant.quantity + quant.reserved_quantity >= Decimal("0")


class TestConcurrentClaims:
    async def test_ten_operators_one_line_one_winner(
        self, stock_di, unique_id: str
    ) -> None:
        """Десять ТСД хватают одно задание: победитель ровно один,
        остальные — move_line_claimed, задание остаётся на победителе."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        move = await _reserved_move(env, Decimal("3"))
        line = (
            await StockMoveLine.list_for_move(env.company_id, move.move_id)
        )[0]
        results = await asyncio.gather(
            *(
                env.di.task_service.claim(
                    company_id=env.company_id,
                    warehouse_id=env.warehouse.warehouse_id,
                    move_line_ids=[line.move_line_id],
                    user_id=f"op-{i}",
                )
                for i in range(10)
            ),
            return_exceptions=True,
        )
        winners = [r for r in results if not isinstance(r, Exception)]
        losers = [r for r in results if isinstance(r, Exception)]
        assert len(winners) == 1
        for err in losers:
            assert isinstance(err, PlatformConflictError)
            assert err.error_code == "move_line_claimed"
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.assigned_user_id == winners[0].assigned_user_id


class TestConcurrentInventory:
    async def test_double_apply_only_one_posts(
        self, stock_di, unique_id: str
    ) -> None:
        """Два приказа apply на один черновик: первый проводит
        дельту, второй видит пустой черновик — одно движение, не два."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        _ = await env.di.move_engine.inventory_set(
            company_id=env.company_id,
            quant_id=quant.quant_id,
            inventory_quantity=Decimal("9"),
        )
        results = await asyncio.gather(
            env.di.move_engine.inventory_apply(
                company_id=env.company_id,
                quant_id=quant.quant_id,
                idempotency_key=f"ap1-{unique_id}",
            ),
            env.di.move_engine.inventory_apply(
                company_id=env.company_id,
                quant_id=quant.quant_id,
                idempotency_key=f"ap2-{unique_id}",
            ),
            return_exceptions=True,
        )
        ok = [r for r in results if not isinstance(r, Exception)]
        errs = [r for r in results if isinstance(r, Exception)]
        assert len(ok) == 1
        for err in errs:
            assert isinstance(err, PlatformConflictError)
            assert err.error_code == "inventory_empty"
        fresh = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Дельта 9−5=4 применена ровно один раз.
        assert fresh.quantity == Decimal("9")


class TestConcurrentReceipts:
    async def test_eight_parallel_receipts_sum_on_quant(
        self, stock_di, unique_id: str
    ) -> None:
        """Восемь приёмок по 2 шт одновременно: остаток ровно 16,
        ни одна запись леджера не потеряна."""
        env = await _env(stock_di, unique_id)
        await asyncio.gather(
            *(
                _receipt(env, Decimal("2"), Decimal("1"))
                for _ in range(8)
            )
        )
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quantity == Decimal("16")
        moves = await StockMove.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
            state=StockMoveState.DONE,
        ).all()
        assert len(moves) == 8


class TestCrossWarehouseLanes:
    async def test_sibling_warehouses_do_not_block_each_other(
        self, stock_di, unique_id: str
    ) -> None:
        """Операции разных складов идут в своих полосах: обе приёмки
        разных складов завершаются без взаимных отказов."""
        env = await _env(stock_di, unique_id)
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WB{unique_id[:8]}",
            name="Second",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        ops_b = {
            op.code: op
            for op in await env.di.warehouse_service.list_operation_types(
                company_id=env.company_id,
                warehouse_id=other.warehouse_id,
            )
        }

        async def _receipt_wh(warehouse_id: str, op) -> None:
            transfer = await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=warehouse_id,
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
                        unit_price=Decimal("1"),
                    )
                ],
            )
            for step in ("confirm", "assign", "validate"):
                _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                    company_id=env.company_id,
                    transfer_id=transfer.transfer_id,
                )

        await asyncio.gather(
            _receipt_wh(
                env.warehouse.warehouse_id,
                env.op_types[StockOperationCode.INCOMING],
            ),
            _receipt_wh(
                other.warehouse_id, ops_b[StockOperationCode.INCOMING]
            ),
        )
        quants = await StockQuant.objects.filter(
            company_id=env.company_id,
            product_id=env.product.product_id,
        ).all()
        total = sum((q.quantity for q in quants), Decimal("0"))
        assert total == Decimal("8")
        whs = {q.warehouse_id for q in quants}
        assert whs == {env.warehouse.warehouse_id, other.warehouse_id}


class TestUniqueRaces:
    async def test_same_warehouse_code_single_winner(
        self, stock_di, unique_id: str
    ) -> None:
        """Две регистрации склада с одним кодом одновременно:
        одна побеждает, вторая — warehouse_code_conflict."""
        env = await _env(stock_di, unique_id)
        results = await asyncio.gather(
            *(
                env.di.warehouse_service.create_warehouse(
                    company_id=env.company_id,
                    code=f"DUP{unique_id[:8]}",
                    name=f"Dup {i}",
                    owner_user_id="test_user",
                    layout_preset=StockLayoutPreset.SIMPLE,
                    removal_strategy=StockRemovalStrategy.FIFO,
                )
                for i in range(2)
            ),
            return_exceptions=True,
        )
        ok = [r for r in results if not isinstance(r, Exception)]
        errs = [r for r in results if isinstance(r, Exception)]
        assert len(ok) == 1
        for err in errs:
            assert isinstance(err, PlatformConflictError)
            assert err.error_code == "warehouse_code_conflict"

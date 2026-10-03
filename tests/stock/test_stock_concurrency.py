"""Конкурентность полосы склада: параллельные резервы, проводки и
фоновая сверка не могут увести остаток в минус, потерять запись
ledgеra или дважды провести один документ — сериализация lane.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from apps.stock.models import (
    StockMove,
    StockMoveLine,
    StockMoveState,
    StockOperationCode,
    ValuationMethod,
)
from apps.stock.models.common import StockMoveSpec
from core.errors.boundary import PlatformConflictError
from tests.stock.test_stock_domain import StockEnv, _make_env, _receipt, _stock_quant


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
    )


async def _make_delivery(env: StockEnv, qty: Decimal) -> str:
    """Черновик+confirm исходящей накладной; возвращает transfer_id."""
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
            )
        ],
    )
    _ = await env.di.move_engine.confirm_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    return transfer.transfer_id


async def _open_reserved(env: StockEnv) -> Decimal:
    """Сумма резерва по всем открытым строкам продукта.

    ``line.quantity`` — зарезервированный объём строки (на reserve
    ``done_quantity`` дублирует её как «подсказку» кладовщику —
    факт исполнения уточняется на проводке).
    """
    from apps.stock.models import StockMoveLineState

    lines = await StockMoveLine.objects.filter(
        company_id=env.company_id, product_id=env.product.product_id
    ).all()
    return sum(
        (
            ln.quantity
            for ln in lines
            if ln.state == StockMoveLineState.OPEN
        ),
        Decimal("0"),
    )


class TestConcurrentReservations:
    async def test_parallel_assigns_never_overreserve(
        self, stock_di, unique_id: str
    ) -> None:
        """Два оператора резервируют одни и те же 10 шт под 8+8.

        Полоса склада сериализует резервы: сумма зарезервированного по
        строкам никогда не превысит физический остаток, quant не уйдёт
        в минус — второй получит частичный резерв или ничего.
        """
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("10"), Decimal("5"))
        t1 = await _make_delivery(env, Decimal("8"))
        t2 = await _make_delivery(env, Decimal("8"))

        await asyncio.gather(
            env.di.move_engine.assign_transfer(
                company_id=env.company_id, transfer_id=t1
            ),
            env.di.move_engine.assign_transfer(
                company_id=env.company_id, transfer_id=t2
            ),
        )

        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity - quant.reserved_quantity >= 0
        reserved = await _open_reserved(env)
        assert reserved <= Decimal("10")
        assert reserved > 0  # хотя бы один резерв прошёл

    async def test_five_parallel_assigns_serialize(
        self, stock_di, unique_id: str
    ) -> None:
        """Пять конкурирующих резервов по 3 шт на остаток 10: итог ≤10."""
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("10"), Decimal("5"))
        transfers = [
            await _make_delivery(env, Decimal("3")) for _ in range(5)
        ]
        await asyncio.gather(
            *(
                env.di.move_engine.assign_transfer(
                    company_id=env.company_id, transfer_id=tid
                )
                for tid in transfers
            )
        )
        reserved = await _open_reserved(env)
        assert reserved <= Decimal("10")
        assert reserved >= Decimal("9")  # три полных плюс частичка


class TestConcurrentValidation:
    async def test_parallel_validations_post_exactly(
        self, stock_di, unique_id: str
    ) -> None:
        """Две накладные проводятся одновременно — обе доходят до done.

        Каждая проводка — отдельная транзакция полосы: суммарная
        отгрузка ровно 10, остаток 0, ни одна запись не потеряна
        и не задублирована.
        """
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("10"), Decimal("5"))
        t1 = await _make_delivery(env, Decimal("4"))
        t2 = await _make_delivery(env, Decimal("6"))
        await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=t1
        )
        await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=t2
        )

        await asyncio.gather(
            env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=t1
            ),
            env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=t2
            ),
        )

        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == 0
        for tid in (t1, t2):
            moves = await StockMove.list_for_transfer(env.company_id, tid)
            assert any(m.state == StockMoveState.DONE for m in moves)

    async def test_double_validate_same_transfer_is_safe(
        self, stock_di, unique_id: str
    ) -> None:
        """Повторная проводка той же накладной не дублирует запись.

        Параллельные ``validate`` с разными ключами идемпотентности:
        вторая видит уже-проведённое состояние и конфликтует либо
        отвечает no-op — но остаток списывается строго один раз.
        """
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("10"), Decimal("5"))
        tid = await _make_delivery(env, Decimal("4"))
        await env.di.move_engine.assign_transfer(
            company_id=env.company_id, transfer_id=tid
        )

        results = await asyncio.gather(
            env.di.move_engine.validate_transfer(
                company_id=env.company_id,
                transfer_id=tid,
                idempotency_key="val-1",
            ),
            env.di.move_engine.validate_transfer(
                company_id=env.company_id,
                transfer_id=tid,
                idempotency_key="val-2",
            ),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, Exception)]
        for err in errors:
            assert isinstance(err, PlatformConflictError)

        quant = await _stock_quant(env)
        assert quant is not None
        # отгрузка 4 списана ровно один раз
        assert quant.quantity == Decimal("6")
        moves = await StockMove.list_for_transfer(env.company_id, tid)
        assert sum(
            m.product_uom_qty
            for m in moves
            if m.state == StockMoveState.DONE
        ) <= Decimal("4")


class TestMaintenanceRace:
    async def test_reconcile_during_reserve_keeps_books(
        self, stock_di, unique_id: str
    ) -> None:
        """Сверка резервов в момент активного резервирования не ломает
        ни операцию, ни сверку: итоговое состояние консистентно.
        """
        env = await _env(stock_di, unique_id)
        await _receipt(env, Decimal("10"), Decimal("5"))
        transfers = [
            await _make_delivery(env, Decimal("4")) for _ in range(3)
        ]

        async def _assign_all() -> None:
            for tid in transfers:
                await env.di.move_engine.assign_transfer(
                    company_id=env.company_id, transfer_id=tid
                )

        await asyncio.gather(
            _assign_all(),
            env.di.maintenance_service.reconcile_warehouse(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
            ),
        )

        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity - quant.reserved_quantity >= 0
        # после сверки резерв на quant == сумме резервов открытых строк
        reserved = await _open_reserved(env)
        assert quant.reserved_quantity == reserved

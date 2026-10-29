"""Матрица кодов ошибок — контракт отказов на границах домена.

Каждый тест доводит сценарий до точки, где бизнес-инвариант обязан
остановить операцию, и фиксирует конкретный ``error_code``. Это
страховка от «тихих» отказов: мутирующая операция либо проходит
целиком, либо падает с кодом, по которому клиент и бухгалтерия
понимают, что именно было нарушено.
"""

from decimal import Decimal

import pytest

from apps.stock.models.api import StockMoveSpec
from apps.stock.models.enums import (
    StockLayoutPreset,
    StockLocationUsage,
    StockOperationCode,
    StockPartnerRole,
    StockRemovalStrategy,
    StockTracking,
    ValuationMethod,
)
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.route import StockRouteStepSpec
from apps.stock.models.scan import ScanContext, ScanFlow, ScanLineDraft
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)

from .test_stock_domain import _delivery, _make_env, _receipt, _stock_quant


async def _tracked_env(stock_di, unique_id: str, tracking: StockTracking):
    """Склад + продукт с трассировкой (партия/серийник)."""
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


async def _lot(stock_di, env, name: str):
    return await stock_di.catalog_service.create_lot(
        company_id=env.company_id,
        product_id=env.product.product_id,
        name=name,
        barcode=None,
        expiration_at=None,
    )


async def _open_inbound(env, qty: Decimal) -> str:
    """INCOMING накладная до assigned (строка резерва открыта).

    Возвращает transfer_id.
    """
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
    return transfer.transfer_id


async def _open_line(env, transfer_id: str) -> StockMoveLine:
    moves = await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer_id)
    lines = await StockMoveLine.list_for_moves_by_created_at_asc(
        env.company_id, [m.move_id for m in moves]
    )
    return lines[0]


# ---------------------------------------------------------------------------
# Накладные и движения: сущности и состояния
# ---------------------------------------------------------------------------


class TestTransferMoveErrors:
    """not_found / state-конфликты на жизненном цикле документа."""

    async def test_transfer_not_found_on_all_steps(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        calls = {
            "confirm": {},
            "assign": {},
            "validate": {},
            "cancel": {},
            "return": {"move_quantities": None},
        }
        for step, extra in calls.items():
            with pytest.raises(PlatformNotFoundError) as exc_transfer_not_found:
                await getattr(
                    env.di.move_engine, f"{step}_transfer"
                )(
                    company_id=env.company_id,
                    transfer_id="trs-bogus",
                    **extra,
                )

            assert exc_transfer_not_found.value.error_code == "transfer_not_found"
    async def test_move_not_found(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_move_not_found:
            await env.di.move_engine.unreserve_move(
                company_id=env.company_id, move_id="mov-bogus"
            )

        assert exc_move_not_found.value.error_code == "move_not_found"
    async def test_move_state_conflict_confirm_done(
        self, stock_di, unique_id: str
    ) -> None:
        """Проведённая накладная не «подтверждается» заново:
        confirm на done-move — конфликт состояния."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _receipt(env, Decimal("5"), Decimal("10"))
        with pytest.raises(PlatformConflictError) as exc_move_state_conflict:
            await env.di.move_engine.confirm_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )

        assert exc_move_state_conflict.value.error_code == "move_state_conflict"
    async def test_confirm_assigned_state_conflict(
        self, stock_di, unique_id: str
    ) -> None:
        """Confirm — шаг «draft → confirmed». Уже зарезервированная
        накладная (assigned) вернуться на шаг назад не может —
        состояние только вперёд."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("5"))
        with pytest.raises(PlatformConflictError) as exc_move_state_conflict:
            await env.di.move_engine.confirm_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )

        assert exc_move_state_conflict.value.error_code == "move_state_conflict"
    async def test_transfer_done_cancel_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """Проведённую накладную нельзя отменить — только возврат."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _receipt(env, Decimal("5"), Decimal("10"))
        with pytest.raises(PlatformConflictError) as exc_transfer_done:
            await env.di.move_engine.cancel_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )

        assert exc_transfer_done.value.error_code == "transfer_done"
    async def test_transfer_not_done_return_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """Возврат строится только на проведённой накладной."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("5"), Decimal("10"))
        open_delivery_id = await self._assigned_delivery(env)
        with pytest.raises(PlatformConflictError) as exc_transfer_not_done:
            await env.di.move_engine.return_transfer(
                company_id=env.company_id,
                transfer_id=open_delivery_id,
                move_quantities=None,
            )

        assert exc_transfer_not_done.value.error_code == "transfer_not_done"
    async def _assigned_delivery(self, env) -> str:
        """Исходящая накладная до assigned, без проводки."""
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
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        return transfer.transfer_id

    async def test_move_closed_blocks_update_line(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _receipt(env, Decimal("3"), Decimal("10"))
        line = await _open_line(env, transfer_id)
        with pytest.raises(PlatformConflictError) as exc_move_closed:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=Decimal("1"),
                picked=None,
                lot_id=None,
                location_dest_id=None,
            )

        assert exc_move_closed.value.error_code == "move_closed"
    async def test_operation_type_warehouse_mismatch(
        self, stock_di, unique_id: str
    ) -> None:
        """Тип операции чужого склада не принимается — накладная
        не должна «ехать» по чужому процессу."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh_b = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WB{unique_id[:8]}",
            name=f"Warehouse B {unique_id}",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        incoming = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformConflictError) as exc_operation_type_warehouse_mismatch:
            await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=wh_b.warehouse_id,
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
                        product_qty=Decimal("1"),
                        uom_id=env.uom_id,
                    )
                ],
            )

        assert exc_operation_type_warehouse_mismatch.value.error_code == "operation_type_warehouse_mismatch"
    async def test_scan_commit_on_closed_move(
        self, stock_di, unique_id: str
    ) -> None:
        """Скан-коммит в проведённый move → move_state_conflict."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _receipt(env, Decimal("2"), Decimal("10"))
        move = (
            await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer_id)
        )[0]
        with pytest.raises(PlatformConflictError) as exc_move_state_conflict:
            await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id=move.move_id,
                context=ScanContext(
                    flow=ScanFlow.PICK,
                    lines=(
                        ScanLineDraft(
                            location_id=None,
                            location_dest_id=None,
                            product_id=env.product.product_id,
                            quantity=Decimal("1"),
                        ),
                    ),
                ),
            )

        assert exc_move_state_conflict.value.error_code == "move_state_conflict"
    async def test_scan_commit_move_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_move_not_found:
            await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id="mov-bogus",
                context=ScanContext(
                    flow=ScanFlow.PICK,
                    lines=(
                        ScanLineDraft(
                            location_id=None,
                            location_dest_id=None,
                            product_id=env.product.product_id,
                            quantity=Decimal("1"),
                        ),
                    ),
                ),
            )

        assert exc_move_not_found.value.error_code == "move_not_found"
    async def test_scan_nothing_to_commit(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc_scan_nothing_to_commit:
            await env.di.scan_service.commit(
                company_id=env.company_id,
                move_id="mov-any",
                context=ScanContext(flow=ScanFlow.PICK),
            )


        assert exc_scan_nothing_to_commit.value.error_code == "scan_nothing_to_commit"
# ---------------------------------------------------------------------------
# Строки движения: факт исполнения
# ---------------------------------------------------------------------------


class TestMoveLineErrors:
    """Проверки записей факта — done, exception, не-открытая строка."""

    async def test_move_line_not_found_update(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_move_line_not_found:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id="mli-bogus",
                done_quantity=Decimal("1"),
                picked=None,
                lot_id=None,
                location_dest_id=None,
            )

        assert exc_move_line_not_found.value.error_code == "move_line_not_found"
    async def test_move_line_not_found_exception(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_move_line_not_found:
            await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id="mli-bogus",
                shortage=Decimal("1"),
                reason="missing",
                actor_user_id="test_user",
            )

        assert exc_move_line_not_found.value.error_code == "move_line_not_found"
    async def test_move_line_not_open_on_exception(
        self, stock_di, unique_id: str
    ) -> None:
        """Исключение по закрытой (проведённой) строке — поздний
        сигнал, отклонён."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _receipt(env, Decimal("3"), Decimal("10"))
        line = await _open_line(env, transfer_id)
        with pytest.raises(PlatformConflictError) as exc_move_line_not_open:
            await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id=line.move_line_id,
                shortage=Decimal("1"),
                reason="missing",
                actor_user_id="test_user",
            )

        assert exc_move_line_not_open.value.error_code == "move_line_not_open"
    async def test_move_line_exception_qty_over(
        self, stock_di, unique_id: str
    ) -> None:
        """Недостача больше зарезервированного — нельзя «снять»
        больше, чем строка обещала."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("4"))
        line = await _open_line(env, transfer_id)
        with pytest.raises(PlatformConflictError) as exc_move_line_exception_qty:
            await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id=line.move_line_id,
                shortage=Decimal("99"),
                reason="missing",
                actor_user_id="test_user",
            )

        assert exc_move_line_exception_qty.value.error_code == "move_line_exception_qty"
    async def test_move_line_exception_qty_zero(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("4"))
        line = await _open_line(env, transfer_id)
        with pytest.raises(PlatformConflictError) as exc_move_line_exception_qty:
            await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id=line.move_line_id,
                shortage=Decimal("0"),
                reason="missing",
                actor_user_id="test_user",
            )

        assert exc_move_line_exception_qty.value.error_code == "move_line_exception_qty"
    async def test_done_quantity_invalid(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("4"))
        line = await _open_line(env, transfer_id)
        with pytest.raises(PlatformConflictError) as exc_done_quantity_invalid:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=Decimal("-1"),
                picked=None,
                lot_id=None,
                location_dest_id=None,
            )

        assert exc_done_quantity_invalid.value.error_code == "done_quantity_invalid"
    async def test_location_not_found_on_redirect(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("4"))
        line = await _open_line(env, transfer_id)
        with pytest.raises(PlatformNotFoundError) as exc_location_not_found:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=None,
                location_dest_id="loc-bogus",
            )

        assert exc_location_not_found.value.error_code == "location_not_found"
    async def test_location_usage_invalid_on_redirect(
        self, stock_di, unique_id: str
    ) -> None:
        """Переназначить приём прихода на partner-локацию — «вернуть
        туда, откуда виртуально пришёл» — запрещено: это уничтожило бы
        товар без списания на внутреннем конце."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("4"))
        line = await _open_line(env, transfer_id)
        from apps.stock.services.company_init_service import (
            virtual_location_id,
        )

        # Виртуальная локация поставщика живёт вне склада.
        vendor_id = virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER, StockPartnerRole.VENDOR
        )
        with pytest.raises(PlatformConflictError) as exc_location_usage_invalid:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=None,
                location_dest_id=vendor_id,
            )


        assert exc_location_usage_invalid.value.error_code == "location_usage_invalid"
# ---------------------------------------------------------------------------
# Единицы измерения
# ---------------------------------------------------------------------------


class TestUomErrors:
    """ЕИ-контракты: категория, продуктовая привязка, существование."""

    def _spec(self, env, uom_id: str) -> list[StockMoveSpec]:
        return [
            StockMoveSpec(
                product_id=env.product.product_id,
                product_qty=Decimal("1"),
                uom_id=uom_id,
            )
        ]

    async def test_uom_not_found_on_spec(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        op = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformNotFoundError) as exc_uom_not_found:
            await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_type_id=op.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type=None,
                origin_document_id=None,
                barcode=None,
                moves=self._spec(env, "uom-bogus"),
            )

        assert exc_uom_not_found.value.error_code == "uom_not_found"
    async def test_uom_category_mismatch(
        self, stock_di, unique_id: str
    ) -> None:
        """«5 кг» в строке штучного товара — конверсия между
        несвязанными категориями ЕИ невозможна."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        uoms = await env.di.catalog_service.list_uoms(
            company_id=env.company_id
        )
        kg = next(u for u in uoms if u.name == "kg")
        op = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformConflictError) as exc_uom_category_mismatch:
            await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_type_id=op.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type=None,
                origin_document_id=None,
                barcode=None,
                moves=self._spec(env, kg.uom_id),
            )

        assert exc_uom_category_mismatch.value.error_code == "uom_category_mismatch"
    async def test_uom_product_mismatch(
        self, stock_di, unique_id: str
    ) -> None:
        """Фасовка чужого товара — упаковка жёстко привязана
        к карточке, иначе в остатки попадёт чужая конверсия."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        other = await env.di.catalog_service.create_product(
            company_id=env.company_id,
            name=f"Other {unique_id}",
            sku=f"OTH-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
            barcode=None,
        )
        pack = await env.di.catalog_service.create_packaging(
            company_id=env.company_id,
            product_id=other.product_id,
            name=f"box{unique_id[:4]}",
            quantity=Decimal("10"),
            barcode=None,
            container_type_id=None,
            weight=None,
            volume=None,
        )
        op = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformConflictError) as exc_uom_product_mismatch:
            await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_type_id=op.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type=None,
                origin_document_id=None,
                barcode=None,
                moves=self._spec(env, pack.packaging_id),
            )


        assert exc_uom_product_mismatch.value.error_code == "uom_product_mismatch"
# ---------------------------------------------------------------------------
# Трассировка: партии и серийники
# ---------------------------------------------------------------------------


class TestTrackingErrors:
    """Учёт по партиям/серийникам — фантомная трассировка опаснее
    её отсутствия, поэтому все ветки проверяются на проводке."""

    async def _assigned_lot_move(self, env) -> tuple[str, str]:
        """INCOMING накладная трассируемого товара до assigned.

        Возвращает (transfer_id, move_line_id).
        """
        transfer_id = await _open_inbound(env, Decimal("1"))
        line = await _open_line(env, transfer_id)
        return transfer_id, line.move_line_id

    async def test_lot_required_on_receipt(
        self, stock_di, unique_id: str
    ) -> None:
        """Приёмка партионного товара без партии — проводка
        обязана остановиться: иначе остаток станет безликим."""
        env = await _tracked_env(stock_di, unique_id, StockTracking.LOT)
        transfer_id, _ = await self._assigned_lot_move(env)
        with pytest.raises(PlatformConflictError) as exc_lot_required:
            await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )

        assert exc_lot_required.value.error_code == "lot_required"
    async def test_lot_not_allowed_for_untracked(
        self, stock_di, unique_id: str
    ) -> None:
        """Партия на нетрассируемом товаре — мусор в учёте,
        отклоняется ещё на записи строки."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id = await _open_inbound(env, Decimal("1"))
        line = await _open_line(env, transfer_id)
        lot = await _lot(stock_di, env, f"LOT-{unique_id[:6]}")
        with pytest.raises(PlatformConflictError) as exc_lot_not_allowed:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=lot.lot_id,
                location_dest_id=None,
            )

        assert exc_lot_not_allowed.value.error_code == "lot_not_allowed"
    async def test_lot_not_found(self, stock_di, unique_id: str) -> None:
        env = await _tracked_env(stock_di, unique_id, StockTracking.LOT)
        _, line_id = await self._assigned_lot_move(env)
        with pytest.raises(PlatformNotFoundError) as exc_lot_not_found:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line_id,
                done_quantity=None,
                picked=None,
                lot_id="lot-bogus",
                location_dest_id=None,
            )

        assert exc_lot_not_found.value.error_code == "lot_not_found"
    async def test_lot_product_mismatch(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _tracked_env(stock_di, unique_id, StockTracking.LOT)
        other = await env.di.catalog_service.create_product(
            company_id=env.company_id,
            name=f"Other {unique_id}",
            sku=f"OTH-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.LOT,
            is_storable=True,
            category="general",
            barcode=None,
        )
        foreign = await env.di.catalog_service.create_lot(
            company_id=env.company_id,
            product_id=other.product_id,
            name=f"LOTF-{unique_id[:6]}",
            barcode=None,
            expiration_at=None,
        )
        _, line_id = await self._assigned_lot_move(env)
        with pytest.raises(PlatformConflictError) as exc_lot_product_mismatch:
            await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line_id,
                done_quantity=None,
                picked=None,
                lot_id=foreign.lot_id,
                location_dest_id=None,
            )

        assert exc_lot_product_mismatch.value.error_code == "lot_product_mismatch"
    async def test_serial_quantity_invalid(
        self, stock_di, unique_id: str
    ) -> None:
        """Серийник — это единица. Строка qty=2 по серийному
        товару непроводима."""
        env = await _tracked_env(stock_di, unique_id, StockTracking.SERIAL)
        transfer_id = await _open_inbound(env, Decimal("2"))
        line = await _open_line(env, transfer_id)
        serial = await _lot(stock_di, env, f"SN-{unique_id[:6]}")
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=line.move_line_id,
            done_quantity=None,
            picked=None,
            lot_id=serial.lot_id,
            location_dest_id=None,
        )
        with pytest.raises(PlatformConflictError) as exc_serial_quantity_invalid:
            await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )

        assert exc_serial_quantity_invalid.value.error_code == "serial_quantity_invalid"
    async def test_serial_double_on_hand_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """Один серийник = одна единица на складе. Повторный приход
        того же SN недопустим даже через новую накладную."""
        env = await _tracked_env(stock_di, unique_id, StockTracking.SERIAL)
        serial = await _lot(stock_di, env, f"SN-{unique_id[:6]}")

        async def receipt_with_sn() -> str:
            transfer_id = await _open_inbound(env, Decimal("1"))
            line = await _open_line(env, transfer_id)
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=serial.lot_id,
                location_dest_id=None,
            )
            return transfer_id

        first = await receipt_with_sn()
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=first
        )
        second = await receipt_with_sn()
        with pytest.raises(PlatformConflictError) as exc_serial_quantity_invalid:
            await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=second
            )


        assert exc_serial_quantity_invalid.value.error_code == "serial_quantity_invalid"
# ---------------------------------------------------------------------------
# Инвентаризация
# ---------------------------------------------------------------------------


class TestInventoryErrors:
    async def test_quant_not_found_inventory_set(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_quant_not_found:
            await env.di.move_engine.inventory_set(
                company_id=env.company_id,
                quant_id="qty-bogus",
                inventory_quantity=Decimal("1"),
            )

        assert exc_quant_not_found.value.error_code == "quant_not_found"
    async def test_inventory_qty_invalid(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("5"), Decimal("10"))
        quant = await _stock_quant(env)
        assert quant is not None
        with pytest.raises(PlatformConflictError) as exc_inventory_qty_invalid:
            await env.di.move_engine.inventory_set(
                company_id=env.company_id,
                quant_id=quant.quant_id,
                inventory_quantity=Decimal("-1"),
            )

        assert exc_inventory_qty_invalid.value.error_code == "inventory_qty_invalid"
    async def test_inventory_empty(self, stock_di, unique_id: str) -> None:
        """Применение без черновика подсчёта — проводить нечего."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("5"), Decimal("10"))
        quant = await _stock_quant(env)
        assert quant is not None
        with pytest.raises(PlatformConflictError) as exc_inventory_empty:
            await env.di.move_engine.inventory_apply(
                company_id=env.company_id, quant_id=quant.quant_id
            )

        assert exc_inventory_empty.value.error_code == "inventory_empty"
    async def test_inventory_delta_zero(
        self, stock_di, unique_id: str
    ) -> None:
        """Пересчёт совпал с остатком → дельта 0 отклоняется, чтобы
        журнал не замусоривался нулевыми проводками."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("5"), Decimal("10"))
        quant = await _stock_quant(env)
        assert quant is not None
        _ = await env.di.move_engine.inventory_set(
            company_id=env.company_id,
            quant_id=quant.quant_id,
            inventory_quantity=Decimal("5"),
        )
        with pytest.raises(PlatformConflictError) as exc_inventory_delta_zero:
            await env.di.move_engine.inventory_apply(
                company_id=env.company_id, quant_id=quant.quant_id
            )


        assert exc_inventory_delta_zero.value.error_code == "inventory_delta_zero"
# ---------------------------------------------------------------------------
# Оценка запасов
# ---------------------------------------------------------------------------


class TestValuationErrors:
    async def test_valuation_method_locked(
        self, stock_di, unique_id: str
    ) -> None:
        """Метод оценки заперт после первой проводки: слои посчитаны
        в одном методе, задним числом их не переводят."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("2"), Decimal("10"))
        with pytest.raises(PlatformConflictError) as exc_valuation_method_locked:
            await env.di.catalog_service.update_product(
                company_id=env.company_id,
                product_id=env.product.product_id,
                name=None,
                sku=None,
                barcode=None,
                is_active=None,
                valuation_method=ValuationMethod.AVERAGE,
                standard_price=None,
                tracking=None,
            )

        assert exc_valuation_method_locked.value.error_code == "valuation_method_locked"
    async def test_revalue_empty_stock(
        self, stock_di, unique_id: str
    ) -> None:
        """Переоценка по цене при нулевом остатке — не к чему
        применять, только дельта-стоимость имеет смысл."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc_revalue_empty_stock:
            await env.di.valuation_service.revalue(
                company_id=env.company_id,
                product_id=env.product.product_id,
                value_delta=None,
                new_price=Decimal("10"),
                description="reprice",
            )

        assert exc_revalue_empty_stock.value.error_code == "revalue_empty_stock"
    async def test_revalue_input_invalid(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("2"), Decimal("10"))
        # Ни одного способа.
        with pytest.raises(PlatformConflictError) as exc_revalue_input_invalid:
            await env.di.valuation_service.revalue(
                company_id=env.company_id,
                product_id=env.product.product_id,
                value_delta=None,
                new_price=None,
                description="reprice",
            )
        assert exc_revalue_input_invalid.value.error_code == "revalue_input_invalid"
        # Оба способа сразу.
        with pytest.raises(PlatformConflictError) as exc_revalue_input_invalid:
            await env.di.valuation_service.revalue(
                company_id=env.company_id,
                product_id=env.product.product_id,
                value_delta=Decimal("5"),
                new_price=Decimal("10"),
                description="reprice",
            )

        assert exc_revalue_input_invalid.value.error_code == "revalue_input_invalid"
    async def test_revalue_delta_zero(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("2"), Decimal("10"))
        with pytest.raises(PlatformConflictError) as exc_revalue_delta_zero:
            await env.di.valuation_service.revalue(
                company_id=env.company_id,
                product_id=env.product.product_id,
                value_delta=Decimal("0"),
                new_price=None,
                description="reprice",
            )

        assert exc_revalue_delta_zero.value.error_code == "revalue_delta_zero"
    async def test_layer_not_found_on_correction(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_layer_not_found:
            await env.di.valuation_service.correction(
                company_id=env.company_id,
                origin_layer_id="lyr-bogus",
                quantity_delta=Decimal("1"),
                value_delta=Decimal("0"),
                description="fix",
            )


        assert exc_layer_not_found.value.error_code == "layer_not_found"
# ---------------------------------------------------------------------------
# Волны
# ---------------------------------------------------------------------------


class TestWaveErrors:
    async def test_wave_not_found(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_wave_not_found:
            await env.di.wave_service.release(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                wave_id="wav-bogus",
            )

        assert exc_wave_not_found.value.error_code == "wave_not_found"
    async def test_wave_empty(self, stock_di, unique_id: str) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc_wave_empty:
            await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[],
                move_ids=[],
            )

        assert exc_wave_empty.value.error_code == "wave_empty"
    async def test_wave_move_line_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_move_line_not_found:
            await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=["mli-bogus"],
                move_ids=[],
            )

        assert exc_move_line_not_found.value.error_code == "move_line_not_found"
    async def _assigned_outbound_line(self, env) -> tuple[str, str]:
        """Исходящая накладная до assigned → (transfer_id, line_id)."""
        _ = await _receipt(env, Decimal("5"), Decimal("10"))
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
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        line = await _open_line(env, transfer.transfer_id)
        return transfer.transfer_id, line.move_line_id

    async def test_wave_state_conflict_double_release(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _, line_id = await self._assigned_outbound_line(env)
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line_id],
            move_ids=[],
        )
        _ = await env.di.wave_service.release(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            wave_id=wave.wave_id,
        )
        with pytest.raises(PlatformConflictError) as exc_wave_state_conflict:
            await env.di.wave_service.release(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                wave_id=wave.wave_id,
            )

        assert exc_wave_state_conflict.value.error_code == "wave_state_conflict"
    async def test_wave_line_conflict(self, stock_di, unique_id: str) -> None:
        """Строка уже в другой волне — сменное задание не дублируется."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _, line_id = await self._assigned_outbound_line(env)
        _ = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line_id],
            move_ids=[],
        )
        with pytest.raises(PlatformConflictError) as exc_wave_line_conflict:
            await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line_id],
                move_ids=[],
            )

        assert exc_wave_line_conflict.value.error_code == "wave_line_conflict"
    async def test_wave_stop_duplicate(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        transfer_id, line_id = await self._assigned_outbound_line(env)
        with pytest.raises(PlatformConflictError) as exc_wave_stop_duplicate:
            await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line_id],
                move_ids=[],
                stop_transfer_ids=[transfer_id, transfer_id],
            )

        assert exc_wave_stop_duplicate.value.error_code == "wave_stop_duplicate"
    async def test_wave_stop_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _, line_id = await self._assigned_outbound_line(env)
        with pytest.raises(PlatformNotFoundError) as exc_transfer_not_found:
            await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line_id],
                move_ids=[],
                stop_transfer_ids=["trs-bogus"],
            )

        assert exc_transfer_not_found.value.error_code == "transfer_not_found"
    async def test_wave_move_line_not_open(
        self, stock_di, unique_id: str
    ) -> None:
        """Закрытую (проведённую) строку в волну не включить."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        _ = await _receipt(env, Decimal("5"), Decimal("10"))
        delivery_id = await _delivery(env, Decimal("2"))
        line = await _open_line(env, delivery_id)
        with pytest.raises(PlatformConflictError) as exc_move_line_not_open:
            await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                move_ids=[],
            )


        assert exc_move_line_not_open.value.error_code == "move_line_not_open"
# ---------------------------------------------------------------------------
# Локации и контейнеры
# ---------------------------------------------------------------------------


class TestLocationContainerErrors:
    async def test_company_not_initialized(
        self, stock_di, unique_id: str
    ) -> None:
        """Склад без виртуального контура компании: init обязателен
        до первого склада, иначе приходу некуда «прийти из»."""
        with pytest.raises(PlatformConflictError) as exc_company_not_initialized:
            await stock_di.warehouse_service.create_warehouse(
                company_id=f"co-{unique_id}",
                code=f"WH{unique_id[:8]}",
                name=f"Warehouse {unique_id}",
                owner_user_id="test_user",
                layout_preset=StockLayoutPreset.SIMPLE,
                removal_strategy=StockRemovalStrategy.FIFO,
            )

        assert exc_company_not_initialized.value.error_code == "company_not_initialized"
    async def test_warehouse_code_conflict(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc_warehouse_code_conflict:
            await env.di.warehouse_service.create_warehouse(
                company_id=env.company_id,
                code=env.warehouse.code,
                name="Dup",
                owner_user_id="test_user",
                layout_preset=StockLayoutPreset.SIMPLE,
                removal_strategy=StockRemovalStrategy.FIFO,
            )

        assert exc_warehouse_code_conflict.value.error_code == "warehouse_code_conflict"
    async def test_container_type_missing(
        self, stock_di, unique_id: str
    ) -> None:
        """Контейнер без типа тары — система не знает ни габаритов,
        ни правил вложения."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc_container_type_missing:
            await env.di.topology_service.create_location(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                parent_id=env.warehouse.view_location_id,
                name="C",
                usage=StockLocationUsage.CONTAINER,
                barcode=None,
            )

        assert exc_container_type_missing.value.error_code == "container_type_missing"
    async def test_container_not_found_move(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformNotFoundError) as exc_container_not_found:
            await env.di.topology_service.move_container(
                company_id=env.company_id,
                container_id="loc-bogus",
                dest_location_id=env.warehouse.view_location_id,
                user_id="test_user",
            )

        assert exc_container_not_found.value.error_code == "container_not_found"
    async def test_location_parent_invalid(
        self, stock_di, unique_id: str
    ) -> None:
        """Ячейка внутри ячейки — нарушение иерархии хранения:
        bin — листовая точка, детей у неё нет."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh_id = env.warehouse.warehouse_id
        bin_a = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=wh_id,
            parent_id=env.warehouse.view_location_id,
            name="A",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        with pytest.raises(PlatformConflictError) as exc_location_parent_invalid:
            await env.di.topology_service.create_location(
                company_id=env.company_id,
                warehouse_id=wh_id,
                parent_id=bin_a.location_id,
                name="A-inner",
                usage=StockLocationUsage.BIN,
                barcode=None,
            )

        assert exc_location_parent_invalid.value.error_code == "location_parent_invalid"
    async def test_location_usage_invalid_virtual(
        self, stock_di, unique_id: str
    ) -> None:
        """Руками создать partner/adjustment локацию в складе нельзя —
        виртуальные локации рождаются только через company init."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        with pytest.raises(PlatformConflictError) as exc_location_usage_invalid:
            await env.di.topology_service.create_location(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                parent_id=None,
                name="fake-vendor",
                usage=StockLocationUsage.PARTNER,
                barcode=None,
            )

        assert exc_location_usage_invalid.value.error_code == "location_usage_invalid"
    async def test_container_parent_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Тип тары не в allowed_parent_type_ids родителя —
        «мешок нельзя в эту паллету»."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh_id = env.warehouse.warehouse_id
        pallet_t = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=wh_id,
            name=f"pallet-{unique_id[:4]}",
            allowed_parent_type_ids=[],
        )
        bag_t = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=wh_id,
            name=f"bag-{unique_id[:4]}",
            allowed_parent_type_ids=[],
        )
        # Короб, который можно класть только на pallet_t.
        box_t = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=wh_id,
            name=f"box-{unique_id[:4]}",
            allowed_parent_type_ids=[pallet_t.container_type_id],
        )
        bag = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=wh_id,
            parent_location_id=env.warehouse.view_location_id,
            container_type_id=bag_t.container_type_id,
            name=f"bag{unique_id[:4]}",
            barcode=None,
        )
        with pytest.raises(PlatformConflictError) as exc_container_parent_denied:
            await env.di.topology_service.create_container(
                company_id=env.company_id,
                warehouse_id=wh_id,
                parent_location_id=bag.location_id,
                container_type_id=box_t.container_type_id,
                name=f"box{unique_id[:4]}",
                barcode=None,
            )


        assert exc_container_parent_denied.value.error_code == "container_parent_denied"
# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------


class TestRouteErrors:
    async def test_route_step_sequence_duplicate(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        incoming = env.op_types[StockOperationCode.INCOMING]
        step = StockRouteStepSpec(
            sequence=10,
            operation_type_id=incoming.operation_type_id,
        )
        with pytest.raises(PlatformConflictError) as exc_route_step_sequence_duplicate:
            await env.di.rule_service.create_route(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="R",
                code=f"R-{unique_id[:4]}",
                steps=[step, step],
            )

        assert exc_route_step_sequence_duplicate.value.error_code == "route_step_sequence_duplicate"
    async def test_route_step_warehouse_mismatch(
        self, stock_di, unique_id: str
    ) -> None:
        """Локальный маршрут не может шагать через типы операций
        чужого склада — цепочка «разъедется» без транзита."""
        env = await _make_env(
            stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
        )
        wh_b = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WB{unique_id[:8]}",
            name=f"Warehouse B {unique_id}",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        ots_b = await env.di.warehouse_service.list_operation_types(
            company_id=env.company_id, warehouse_id=wh_b.warehouse_id
        )
        foreign = next(
            ot for ot in ots_b if ot.code == StockOperationCode.INCOMING
        )
        with pytest.raises(PlatformConflictError) as exc_route_step_warehouse_mismatch:
            await env.di.rule_service.create_route(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="R",
                code=f"R{unique_id[:4]}",
                steps=[
                    StockRouteStepSpec(
                        sequence=10,
                        operation_type_id=foreign.operation_type_id,
                    )
                ],
            )

        assert exc_route_step_warehouse_mismatch.value.error_code == "route_step_warehouse_mismatch"

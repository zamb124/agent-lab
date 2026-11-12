"""Очередь заданий склада — захват, раздача, исключения, волны.

Бизнес-правила под тестом:

* ``next`` — «дать работу»: голова очереди по приоритету, фильтр
  возможностей ресурса, захват в той же полосе — два ТСД не получат
  одно поручение;
* ``claim``/``assign`` — атомарные: любая «битая» строка пакета
  отклоняет захват целиком (никому не достаётся «ползадания»);
* ``release`` — оператор отпускает только своё; диспетчер
  (``user_id=None``) может снимать чужие захваты;
* ``report_exception`` — недостача укорачивает строку и ``done``,
  освобождает резерв ровно на недостачу и ставит пересчёт ячейки;
* ``update_move_line`` — правка только на открытом move, концы
  строки обязаны держать класс направления документа;
* волны — пустая не создаётся, строка живёт в одной волне, путевой
  лист проверяет склад каждой остановки, release только из draft.
"""

import uuid
from decimal import Decimal

import pytest

from apps.stock.models.common import STOCK_DB, StockMoveSpec
from apps.stock.models.enums import (
    StockLayoutPreset,
    StockLocationUsage,
    StockMoveLineKind,
    StockOperationCode,
    StockPartnerRole,
    StockRemovalStrategy,
    StockWaveState,
    ValuationMethod,
)
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.quant import StockQuant
from apps.stock.models.resource import StockResource
from apps.stock.models.wave import StockWave
from apps.stock.services.company_init_service import virtual_location_id
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.files.models import FileRecord
from core.lanes import LaneCommit

from .test_stock_domain import StockEnv, _make_env, _receipt


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
    )


async def _reserved_delivery_line(env: StockEnv, qty: Decimal) -> StockMoveLine:
    """Исходящая накладная confirm+assign → открытая строка резерва."""
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
    lines = await StockMoveLine.list_open_for_move_by_created_at_asc(env.company_id, moves[0].move_id)
    assert lines, "ожидалась строка резерва"
    return lines[0]


async def _resource(
    env: StockEnv, suffix: str, *, active: bool = True, **type_kwargs
):
    """Тип + единица техники для проверок допуска заданий."""
    rtype = await env.di.topology_service.create_resource_type(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        name=f"RT-{suffix}",
        allowed_container_type_ids=type_kwargs.get(
            "allowed_container_type_ids", []
        ),
        storage_type_ids=type_kwargs.get("storage_type_ids", []),
        handles_loose=type_kwargs.get("handles_loose", True),
        max_level=type_kwargs.get("max_level"),
    )
    resource = await env.di.topology_service.create_resource(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        resource_type_id=rtype.resource_type_id,
        code=f"RES-{suffix}",
        barcode=None,
    )
    if not active:
        _ = await StockResource.objects.filter(
            company_id=env.company_id, resource_id=resource.resource_id
        ).update(using=STOCK_DB, is_active=False)
    return resource


class TestNextLine:
    async def test_empty_queue_returns_none(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        result = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
        )
        assert result is None

    async def test_next_claims_head_and_hides_from_others(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))

        first = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
        )
        assert first is not None
        assert first.move_line_id == line.move_line_id
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.assigned_user_id == "op-1"

        # Чужой оператор не видит занятую строку.
        other = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-2",
        )
        assert other is None
        # Сам оператор получает своё же задание повторно.
        mine = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
        )
        assert mine is not None and mine.move_line_id == line.move_line_id

    async def test_next_without_claim_leaves_line_free(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))

        peek = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
            claim=False,
        )
        assert peek is not None
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.assigned_user_id is None

    async def test_next_unknown_resource_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        _ = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.next_line(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                user_id="op-1",
                resource_id="src_missing",
            )
        assert exc.value.error_code == "resource_not_found"

    async def test_next_skips_lines_resource_cannot_handle(
        self, stock_di, unique_id: str
    ) -> None:
        """Штабелёр без россыпи не получает quantity-задание."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        _ = await _reserved_delivery_line(env, Decimal("3"))
        forklift = await _resource(
            env, f"nl-{unique_id}", handles_loose=False
        )
        chosen = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
            resource_id=forklift.resource_id,
        )
        assert chosen is None


class TestClaimAssignRelease:
    async def test_claim_missing_line(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=["mli_missing"],
                user_id="op-1",
            )
        assert exc.value.error_code == "move_line_not_found"

    async def test_claim_batch_atomic_reject(
        self, stock_di, unique_id: str
    ) -> None:
        """Одна занятая строка в пакете → весь пакет отклонён,
        свободная строка не остаётся «полузахваченной»."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("9"), Decimal("2"))
        line_a = await _reserved_delivery_line(env, Decimal("3"))
        line_b = await _reserved_delivery_line(env, Decimal("4"))
        _ = await env.di.task_service.claim(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line_b.move_line_id],
            user_id="op-2",
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line_a.move_line_id, line_b.move_line_id],
                user_id="op-1",
            )
        assert exc.value.error_code == "move_line_claimed"
        a = await StockMoveLine.by_id(env.company_id, line_a.move_line_id)
        assert a.assigned_user_id is None

    async def test_claim_done_line_conflict(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        move = await StockMove.by_id(env.company_id, line.move_id)
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=move.transfer_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-1",
            )
        assert exc.value.error_code == "move_line_not_open"

    async def test_claim_with_missing_and_inactive_resource(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-1",
                resource_id="src_missing",
            )
        assert exc.value.error_code == "resource_not_found"
        dead = await _resource(env, f"dead-{unique_id}", active=False)
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-1",
                resource_id=dead.resource_id,
            )
        assert exc.value.error_code == "resource_inactive"

    async def test_claim_with_unfit_resource_denied(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        forklift = await _resource(
            env, f"unfit-{unique_id}", handles_loose=False
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-1",
                resource_id=forklift.resource_id,
            )
        assert exc.value.error_code == "resource_loose_denied"

    async def test_claim_reclaim_by_same_operator_ok(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        for _ in range(2):
            result = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-1",
            )
            assert result.assigned_user_id == "op-1"

    async def test_assign_records_assignee_and_resource(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        cart = await _resource(env, f"asg-{unique_id}")
        result = await env.di.task_service.assign(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line.move_line_id],
            assignee_user_id="op-9",
            resource_id=cart.resource_id,
            actor_user_id="dispatcher",
        )
        assert result.assigned_user_id == "op-9"
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.assigned_user_id == "op-9"
        assert fresh.resource_id == cart.resource_id

    async def test_release_foreign_line_denied_but_dispatcher_ok(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        _ = await env.di.task_service.claim(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line.move_line_id],
            user_id="op-1",
        )
        # Чужой оператор не может отпустить моё задание.
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.release(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[line.move_line_id],
                user_id="op-2",
                actor_user_id="op-2",
            )
        assert exc.value.error_code == "move_line_claimed"
        # Диспетчер (user_id=None) снимает чужой захват.
        _ = await env.di.task_service.release(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_ids=[line.move_line_id],
            user_id=None,
            actor_user_id="dispatcher",
        )
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.assigned_user_id is None
        assert fresh.claimed_at is None

    async def test_release_missing_line_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.release(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=["mli_missing"],
                user_id=None,
                actor_user_id="dispatcher",
            )
        assert exc.value.error_code == "move_line_not_found"


class TestReportException:
    async def test_shortage_out_of_range(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        for bad in (Decimal("0"), Decimal("-1"), Decimal("4")):
            with pytest.raises(PlatformConflictError) as exc:
                _ = await env.di.task_service.report_exception(
                    company_id=env.company_id,
                    warehouse_id=env.warehouse.warehouse_id,
                    move_line_id=line.move_line_id,
                    shortage=bad,
                    reason="bad",
                    actor_user_id="op-1",
                )
            assert exc.value.error_code == "move_line_exception_qty"

    async def test_shortage_missing_and_closed_line(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id="mli_missing",
                shortage=Decimal("1"),
                reason="x",
                actor_user_id="op-1",
            )
        assert exc.value.error_code == "move_line_not_found"
        # Исполненная строка — исправлять нечего.
        move = await StockMove.by_id(env.company_id, line.move_id)
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=move.transfer_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id=line.move_line_id,
                shortage=Decimal("1"),
                reason="x",
                actor_user_id="op-1",
            )
        assert exc.value.error_code == "move_line_not_open"

    async def test_full_shortage_zeroes_line_and_frees_reserve(
        self, stock_di, unique_id: str
    ) -> None:
        """Недостача = вся строка: требование обнуляется, резерв
        ячейки отпускается целиком, задание пересчёта создано."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("4"))
        exc_result = await env.di.task_service.report_exception(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_id=line.move_line_id,
            shortage=Decimal("4"),
            reason="empty_shelf",
            actor_user_id="op-1",
        )
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.quantity == Decimal("0")
        assert fresh.done_quantity == Decimal("0")
        count_line = await StockMoveLine.by_id(
            env.company_id, exc_result.count_line_id
        )
        assert count_line is not None
        assert count_line.kind == StockMoveLineKind.COUNT
        assert count_line.location_id == line.location_id
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=line.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Книжный остаток не тронут — только резерв снят.
        assert quant.quantity == Decimal("6")
        assert quant.reserved_quantity == Decimal("0")

    async def test_exception_clamps_done_quantity(
        self, stock_di, unique_id: str
    ) -> None:
        """Оператор успел отсканировать 3 из 5, потом недостача 4:
        done урезается до оставшегося 1 — post не увезёт «воздух»."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("8"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("5"))
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=line.move_line_id,
            done_quantity=Decimal("3"),
            picked=None,
            lot_id=None,
            location_dest_id=None,
        )
        _ = await env.di.task_service.report_exception(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_id=line.move_line_id,
            shortage=Decimal("4"),
            reason="damaged",
            actor_user_id="op-1",
        )
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.quantity == Decimal("1")
        assert fresh.done_quantity == Decimal("1")

    async def test_exception_attachments_ride_event_payload(
        self, stock_di, unique_id: str
    ) -> None:
        """Фото доказательства уезжают в push исключения — эскалация
        в flows показывает менеджеру бой без второго запроса."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        photo = await FileRecord.objects.create(
            instance=FileRecord(
                file_id=f"file_{unique_id}_exc",
                original_name="damage.jpg",
                s3_key=f"stock/{unique_id}/damage.jpg",
                storage_id="platform",
                content_type="image/jpeg",
                file_size=1024,
                company_id=env.company_id,
            )
        )
        key = uuid.uuid7().hex
        _ = await env.di.task_service.report_exception(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            move_line_id=line.move_line_id,
            shortage=Decimal("2"),
            reason="damaged",
            actor_user_id="op-1",
            file_ids=[photo.file_id],
            idempotency_key=key,
        )
        commit = await LaneCommit.by_idempotency_key(
            env.company_id, key, using=STOCK_DB
        )
        assert commit is not None
        events = {
            event.type: event for event in commit.platform_events()
        }
        payload = events["stock/move_line/exception"].payload
        assert payload["file_ids"] == [photo.file_id]

    async def test_exception_attachment_ghost_file_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """Ссылка на несуществующий файл не проходит — исключение
        не создаётся с битым доказательством."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.report_exception(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_id=line.move_line_id,
                shortage=Decimal("1"),
                reason="damaged",
                actor_user_id="op-1",
                file_ids=["file_ghost"],
            )
        assert exc.value.error_code == "file_not_found"
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.quantity == Decimal("3")


class TestUpdateMoveLine:
    async def test_negative_done_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=Decimal("-1"),
                picked=None,
                lot_id=None,
                location_dest_id=None,
            )
        assert exc.value.error_code == "done_quantity_invalid"

    async def test_update_on_closed_move_denied(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        move = await StockMove.by_id(env.company_id, line.move_id)
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=move.transfer_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=Decimal("1"),
                picked=None,
                lot_id=None,
                location_dest_id=None,
            )
        assert exc.value.error_code == "move_closed"

    async def test_update_missing_line(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id="mli_missing",
                done_quantity=Decimal("1"),
                picked=None,
                lot_id=None,
                location_dest_id=None,
            )
        assert exc.value.error_code == "move_line_not_found"

    async def test_lot_on_untracked_product_denied(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id="lot_any",
                location_dest_id=None,
            )
        assert exc.value.error_code == "lot_not_allowed"

    async def test_dest_to_view_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Зона-view не хранит остатков: строку нельзя «сдать в зону»."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=None,
                location_dest_id=env.warehouse.view_location_id,
            )
        assert exc.value.error_code == "location_usage_invalid"

    async def test_dest_crossing_external_boundary_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Внутренний move: приёмник строки на partner — тихое
        уничтожение стока мимо леджера, отклоняем."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        internal = env.op_types[StockOperationCode.INTERNAL]
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-UML-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
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
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                    location_dest_id=bin_b.location_id,
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
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(
            env.company_id, moves[0].move_id
        )
        partner = virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER,
            StockPartnerRole.CUSTOMER,
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=lines[0].move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=None,
                location_dest_id=partner,
            )
        assert exc.value.error_code == "location_usage_invalid"

    async def test_dest_missing_location(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.update_move_line(
                company_id=env.company_id,
                move_line_id=line.move_line_id,
                done_quantity=None,
                picked=None,
                lot_id=None,
                location_dest_id="loc_missing",
            )
        assert exc.value.error_code == "location_not_found"

    async def test_happy_path_done_and_picked(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        updated = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=line.move_line_id,
            done_quantity=Decimal("2"),
            picked=True,
            lot_id=None,
            location_dest_id=None,
        )
        assert updated.done_quantity == Decimal("2")
        assert updated.picked is True


class TestWavesExtra:
    async def test_empty_wave_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="W-EMPTY",
                move_line_ids=[],
                move_ids=[],
            )
        assert exc.value.error_code == "wave_empty"

    async def test_line_in_two_waves_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        _ = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-1",
            move_line_ids=[line.move_line_id],
            move_ids=[],
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="W-2",
                move_line_ids=[line.move_line_id],
                move_ids=[],
            )
        assert exc.value.error_code == "wave_line_conflict"

    async def test_duplicate_and_foreign_stops_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="W-DUP",
                move_line_ids=[line.move_line_id],
                move_ids=[],
                stop_transfer_ids=["t1", "t1"],
            )
        assert exc.value.error_code == "wave_stop_duplicate"
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="W-GHOST",
                move_line_ids=[line.move_line_id],
                move_ids=[],
                stop_transfer_ids=["trf_missing"],
            )
        assert exc.value.error_code == "transfer_not_found"
        # Остановка чужого склада — маршрут по чужому DC невозможен.
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WO{unique_id[:8]}",
            name="Other",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        ops = await env.di.warehouse_service.list_operation_types(
            company_id=env.company_id, warehouse_id=other.warehouse_id
        )
        op_out = next(o for o in ops if o.code == StockOperationCode.OUTGOING)
        foreign = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=other.warehouse_id,
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
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                    unit_price=None,
                )
            ],
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.wave_service.create(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="W-XWH",
                move_line_ids=[line.move_line_id],
                move_ids=[],
                stop_transfer_ids=[foreign.transfer_id],
            )
        assert exc.value.error_code == "wave_stop_warehouse_mismatch"

    async def test_release_missing_and_non_draft(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.wave_service.release(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                wave_id="wav_missing",
            )
        assert exc.value.error_code == "wave_not_found"
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-REL",
            move_line_ids=[line.move_line_id],
            move_ids=[],
        )
        _ = await env.di.wave_service.release(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            wave_id=wave.wave_id,
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.wave_service.release(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                wave_id=wave.wave_id,
            )
        assert exc.value.error_code == "wave_state_conflict"

    async def test_wave_user_assignment_and_stop_order(
        self, stock_di, unique_id: str
    ) -> None:
        """Волна «на одного кладовщика»: строки получают assignee,
        приоритет и stop_order по позиции накладной в рейсе."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("9"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        move = await StockMove.by_id(env.company_id, line.move_id)
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-USER",
            move_line_ids=[line.move_line_id],
            move_ids=[],
            priority=7,
            user_id="op-wave",
            stop_transfer_ids=[move.transfer_id],
        )
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.wave_id == wave.wave_id
        assert fresh.priority == 7
        assert fresh.stop_order == 0
        assert fresh.assigned_user_id == "op-wave"

    async def test_wave_done_after_all_lines_posted(
        self, stock_di, unique_id: str
    ) -> None:
        """Все строки волны исполнены → волна сама становится done."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-DONE",
            move_line_ids=[line.move_line_id],
            move_ids=[],
        )
        _ = await env.di.wave_service.release(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            wave_id=wave.wave_id,
        )
        move = await StockMove.by_id(env.company_id, line.move_id)
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=move.transfer_id
        )
        fresh = await StockWave.by_id(env.company_id, wave.wave_id)
        assert fresh.state == StockWaveState.DONE

    async def test_wave_via_move_ids_collects_open_lines(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        line = await _reserved_delivery_line(env, Decimal("3"))
        move = await StockMove.by_id(env.company_id, line.move_id)
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-MOVES",
            move_line_ids=[],
            move_ids=[move.move_id],
        )
        fresh = await StockMoveLine.by_id(env.company_id, line.move_line_id)
        assert fresh.wave_id == wave.wave_id
        assert wave.line_count == 1

    async def test_wave_filter_scopes_queue_and_next(
        self, stock_di, unique_id: str
    ) -> None:
        """Оператор выбрал волну → очередь и «дать работу» живут внутри неё."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("9"), Decimal("2"))
        in_wave = await _reserved_delivery_line(env, Decimal("3"))
        outside = await _reserved_delivery_line(env, Decimal("2"))
        wave = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-SCOPE",
            move_line_ids=[in_wave.move_line_id],
            move_ids=[],
        )
        _ = await env.di.wave_service.release(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            wave_id=wave.wave_id,
        )

        queue = await env.di.task_service.queue(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            wave_id=wave.wave_id,
        )
        assert [line.move_line_id for line in queue] == [in_wave.move_line_id]

        chosen = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
            wave_id=wave.wave_id,
        )
        assert chosen is not None
        assert chosen.move_line_id == in_wave.move_line_id
        fresh = await StockMoveLine.by_id(env.company_id, outside.move_line_id)
        assert fresh.assigned_user_id is None

    async def test_wave_filter_empty_wave_yields_nothing(
        self, stock_di, unique_id: str
    ) -> None:
        """Фильтр по несуществующей/чужой волне — пустая выдача, а не вся очередь."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("6"), Decimal("2"))
        _ = await _reserved_delivery_line(env, Decimal("3"))
        queue = await env.di.task_service.queue(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            wave_id="wav_missing",
        )
        assert queue == []
        chosen = await env.di.task_service.next_line(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
            wave_id="wav_missing",
        )
        assert chosen is None

    async def test_no_wave_filter_returns_all_open_lines(
        self, stock_di, unique_id: str
    ) -> None:
        """Без фильтра оператор видит и волновые, и неволновые строки."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("9"), Decimal("2"))
        in_wave = await _reserved_delivery_line(env, Decimal("3"))
        outside = await _reserved_delivery_line(env, Decimal("2"))
        _ = await env.di.wave_service.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="W-OPEN",
            move_line_ids=[in_wave.move_line_id],
            move_ids=[],
        )
        queue = await env.di.task_service.queue(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
        )
        ids = {line.move_line_id for line in queue}
        assert {in_wave.move_line_id, outside.move_line_id} <= ids

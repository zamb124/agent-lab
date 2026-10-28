"""Фоновое обслуживание склада — тики ``stock_worker``.

Бизнес-инвариант: «все физические правки запасов идут через команды»,
а этот сервис — ночной уборщик: сверяет, что леджер не разъехался,
возвращает брошенные задания в общую очередь, догоняет пополнение
полок и плановый пересчёт.

Каждая правка идёт в полосе склада (``stock_command_lane``) — тик
не может пересечься с рабочей проводкой: сериализация общая.

Состав тиков:

* ``reconcile_warehouse`` — сверка ``reserved_quantity`` на остатках
  с открытыми строками исполнения + дочистка застрявших move;
* ``release_stale_claims`` — освобождение заданий, захваченных и
  брошенных (кладовщик ушёл, задание висит);
* ``reorder_tick`` — min/max правила: остаток упал ниже min →
  черновик пополнения до max;
* ``cycle_count_tick`` — просроченные по ``last_count_at`` ячейки
  получают задания пересчёта (``kind=count`` строки).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from apps.stock.models.common import (
    STOCK_DB,
    STOCK_ZERO,
    StockMoveSpec,
    new_id,
    stock_command_lane,
)
from apps.stock.models.enums import (
    StockMoveLineKind,
    StockMoveLineState,
    StockMoveState,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.operation_type import StockOperationType
from apps.stock.models.quant import StockQuant
from apps.stock.models.reorder_rule import StockReorderRule
from apps.stock.models.transfer import StockTransfer
from apps.stock.models.warehouse import StockWarehouse
from apps.stock.services.move_engine import StockMoveEngine
from core.errors.boundary import PlatformNotFoundError
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models import StrictBaseModel
from core.request_scope import command_idempotency_key
from core.tracing.operation_span import traced_operation
from core.utils.time import utcnow

DEFAULT_CLAIM_TTL = timedelta(hours=8)
"""Задание «в работе» дольше 8 часов — считаем брошенным."""

DEFAULT_CYCLE_COUNT_INTERVAL = timedelta(days=30)
"""Ячейку положено пересчитывать минимум раз в 30 дней."""

CYCLE_COUNT_BINS_PER_TICK = 10
"""За один тик планируем не больше 10 ячеек на склад — равномерно."""


class ReconcileReport(StrictBaseModel):
    """Итог сверки склада — сколько чего починили за тик."""

    warehouse_id: str
    reserved_fixed: int = 0
    """Сколько quant'ов получили исправленный ``reserved_quantity``."""
    moves_closed: int = 0
    """Move'ы, у которых все строки закрыты — добиты до done/cancel."""
    transfers_refreshed: int = 0
    """Документы, чей статус пересчитан из строк заново."""


class ClaimsGcReport(StrictBaseModel):
    warehouse_id: str
    released: int = 0


class CycleCountReport(StrictBaseModel):
    warehouse_id: str
    bins_scheduled: int = 0
    lines_created: int = 0


class MaintenanceService:
    """Оркестратор фоновых тиков — тонкая обвязка над lane-командами."""

    def __init__(self, move_engine: StockMoveEngine) -> None:
        self._moves: StockMoveEngine = move_engine

    # --- Компании и склады ---

    async def list_company_ids(self) -> list[str]:
        return await StockWarehouse.list_company_ids()

    async def _warehouses(self, company_id: str) -> list[StockWarehouse]:
        return await StockWarehouse.list_by_code(
            company_id, limit=500, offset=0
        )

    # --- Reconcile ---

    async def reconcile_warehouse(
        self, *, company_id: str, warehouse_id: str
    ) -> ReconcileReport:
        """Сверка полки с книгой: резервы и застрявшие движения.

        Инвариант, который чиним: ``quant.reserved_quantity`` обязан
        равняться сумме ``quantity`` открытых строк исполнения, севших
        на этот остаток (та же ячейка × товар × партия × владелец).
        Строки ``kind=container`` резервируют контейнер ЦЕЛИКОМ:
        для их поддеревьев ожидаемый резерв = полному остатку.

        Вторая сверка — застрявшие move: все строки закрыты
        (done/cancelled), а шапка ещё assigned — докладываем в done,
        чтобы документ не висел «вечно в работе».
        """
        report = ReconcileReport(warehouse_id=warehouse_id)

        async def body(_scope: LaneScope) -> LaneOutcome[ReconcileReport]:
            lines = await StockMoveLine.list_unordered_open_for_warehouse(
                company_id, warehouse_id
            )
            # Ожидаемый резерв по ключу остатка.
            expected: dict[tuple[str, str, str | None, str | None], Decimal] = (
                defaultdict(lambda: STOCK_ZERO)
            )
            container_roots: set[str] = set()
            for line in lines:
                if line.kind == StockMoveLineKind.COUNT:
                    continue
                if line.kind == StockMoveLineKind.CONTAINER and (
                    line.container_id is not None
                ):
                    container_roots.add(line.container_id)
                    continue
                key = (
                    line.product_id,
                    line.location_id,
                    line.lot_id,
                    line.owner_entity_id,
                )
                expected[key] += line.quantity
            # Резерв «тара целиком» разворачиваем по остаткам поддерева.
            for root_id in container_roots:
                subtree = await StockLocation.list_subtree_ids(
                    company_id, root_id
                )
                inside = await StockQuant.list_for_locations(
                    company_id, subtree, for_update=True
                )
                for quant in inside:
                    expected[
                        (
                            quant.product_id,
                            quant.location_id,
                            quant.lot_id,
                            quant.owner_entity_id,
                        )
                    ] = quant.quantity
            quants = await StockQuant.list_unordered_for_warehouse(
                company_id, warehouse_id
            )
            now = utcnow()
            for quant in quants:
                want = expected.get(
                    (
                        quant.product_id,
                        quant.location_id,
                        quant.lot_id,
                        quant.owner_entity_id,
                    ),
                    STOCK_ZERO,
                )
                if quant.reserved_quantity != want:
                    quant.reserved_quantity = want
                    quant.updated_at = now
                    _ = await quant.save()
                    report.reserved_fixed += 1
            # Застрявшие move: строки все закрыты, шапка «в работе».
            open_moves = await StockMove.list_unordered_confirmed_partial_or_assigned_for_warehouse(
                company_id, warehouse_id
            )
            for move in open_moves:
                all_lines = await StockMoveLine.list_all_for_move(
                    company_id, move.move_id
                )
                if not all_lines:
                    continue
                if any(
                    line.state == StockMoveLineState.OPEN
                    for line in all_lines
                ):
                    continue
                has_done = any(
                    line.state == StockMoveLineState.DONE
                    for line in all_lines
                )
                _ = await StockMove.write_state(
                    company_id,
                    move,
                    StockMoveState.DONE
                    if has_done
                    else StockMoveState.CANCEL,
                )
                report.moves_closed += 1
            # Шапки документов — пересчёт из строк.
            transfer_ids = {
                m.transfer_id for m in open_moves if m.transfer_id
            }
            for tid in transfer_ids:
                _ = await StockTransfer.refresh_state(company_id, tid)
                report.transfers_refreshed += 1
            return LaneOutcome(result=report, events=[])

        run: LaneRun[ReconcileReport] = await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=f"reconcile:{company_id}:{warehouse_id}:{utcnow().strftime('%Y%m%d%H')}",
            command_type="stock/maintenance/reconcile",
            actor_user_id="system",
            result_type=ReconcileReport,
            body=body,
        )
        _ = run
        return report

    # --- Claims GC ---

    async def release_stale_claims(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        claimed_before: datetime,
    ) -> ClaimsGcReport:
        """Отпустить «захвачено и брошено»: строка снова в общей очереди.

        Бизнес-смысл: задание с протухшей отметкой «в работе» теряет
        ``assigned_user_id``/``resource_id``/``claimed_at`` — очередь
        ``next`` раздаст его другому кладовщику. Полоса склада
        гарантирует, что мы не вырвем задание из-под рук оператора,
        который прямо сейчас его проводит.
        """
        report = ClaimsGcReport(warehouse_id=warehouse_id)

        async def body(_scope: LaneScope) -> LaneOutcome[ClaimsGcReport]:
            stale = await StockMoveLine.list_stale_claimed(
                company_id, warehouse_id, claimed_before
            )
            for line in stale:
                await StockMoveLine.clear_claim_fields(
                    company_id, line.move_line_id
                )
                report.released += 1
            return LaneOutcome(result=report, events=[])

        _ = await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=f"claims_gc:{company_id}:{warehouse_id}:{new_id('gc')}",
            command_type="stock/maintenance/claims_gc",
            actor_user_id="system",
            result_type=ClaimsGcReport,
            body=body,
        )
        return report

    # --- Reorder rules ---

    async def reorder_company(self, *, company_id: str) -> int:
        """Min/max пополнение: вернуть число созданных драфтов.

        По каждому активному правилу: остаток поддерева локации
        (``quantity``, без резерва — это полка, а не обещания) ниже
        ``min_qty`` → если открытого заказа по этому правилу нет,
        создаём draft-приход на ``max_qty - остаток`` через обычный
        ``create_transfer`` — дальше он живёт как ручной документ:
        confirm → assign → validate.
        """
        created = 0
        rules = await StockReorderRule.list_by_rule_id(
            company_id, active_only=True
        )
        for rule in rules:
            open_moves = await StockMove.list_open_by_origin(
                company_id, "reorder_rule", rule.rule_id
            )
            if open_moves:
                continue
            subtree = await StockLocation.list_subtree_ids(
                company_id, rule.location_id
            )
            if not subtree:
                continue
            quants = await StockQuant.list_for_locations(
                company_id, subtree
            )
            on_hand = sum(
                (q.quantity for q in quants if q.product_id == rule.product_id),
                STOCK_ZERO,
            )
            if on_hand >= rule.min_qty:
                continue
            need = rule.max_qty - on_hand
            if need <= STOCK_ZERO:
                continue
            ot = await StockOperationType.by_id(
                company_id, rule.operation_type_id
            )
            if ot is None:
                continue
            _ = await self._moves.create_transfer(
                company_id=company_id,
                warehouse_id=rule.warehouse_id,
                operation_type_id=rule.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type="reorder_rule",
                origin_document_id=rule.rule_id,
                barcode=None,
                moves=[
                    StockMoveSpec(
                        product_id=rule.product_id,
                        product_qty=need,
                        uom_id=(await self._product_uom(
                            company_id, rule.product_id
                        )),
                        location_dest_id=rule.location_id,
                        route_id=rule.route_id,
                    )
                ],
                idempotency_key=command_idempotency_key(
                    f"reorder:{rule.rule_id}:{utcnow().date().isoformat()}"
                ),
                actor_user_id="system",
                command_type="stock/transfers/create_requested",
            )
            created += 1
        return created

    async def _product_uom(self, company_id: str, product_id: str) -> str:
        from apps.stock.models.product import StockProduct

        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise PlatformNotFoundError(
                "Product not found", error_code="product_not_found"
            )
        return product.uom_id

    # --- Cycle count ---

    async def cycle_count_warehouse(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        due_before: datetime,
        limit: int = CYCLE_COUNT_BINS_PER_TICK,
    ) -> CycleCountReport:
        """Запланировать пересчёт просроченных ячеек склада.

        Для каждой выбранной ячейки, по каждому товару на ней —
        count-строка ``kind=count`` на отдельном move в ``confirmed``
        (задание видно в очереди оператора, но не двигает остатки).
        Факт заполняется потоком ``count`` сканера → ``inventory_set``,
        дельта проводится ``inventory_apply``. ``last_count_at`` ячейки
        обновляется в момент записи факта — так просрочка считается от
        реального пересчёта, а не от планирования.
        """
        report = CycleCountReport(warehouse_id=warehouse_id)

        async def body(_scope: LaneScope) -> LaneOutcome[CycleCountReport]:
            bins = await StockLocation.list_count_bins(
                company_id, warehouse_id, due_before=due_before, limit=limit
            )
            now = utcnow()
            for bin_loc in bins:
                subtree = await StockLocation.list_subtree_ids(
                    company_id, bin_loc.location_id
                )
                quants = await StockQuant.list_for_locations(
                    company_id, subtree
                )
                products = sorted(
                    {q.product_id for q in quants if q.quantity > STOCK_ZERO}
                )
                if not products:
                    continue
                report.bins_scheduled += 1
                for product_id in products:
                    move = await StockMove.create(
                        StockMove(
                            move_id=new_id("mov"),
                            company_id=company_id,
                            warehouse_id=warehouse_id,
                            transfer_id=None,
                            product_id=product_id,
                            product_qty=STOCK_ZERO,
                            product_uom_qty=STOCK_ZERO,
                            uom_id=(await self._product_uom(
                                company_id, product_id
                            )),
                            location_id=bin_loc.location_id,
                            location_dest_id=bin_loc.location_id,
                            state=StockMoveState.CONFIRMED,
                            operation_type_id=None,
                            origin_document_type="cycle_count",
                            origin_document_id=bin_loc.location_id,
                            date=now,
                            created_at=now,
                        )
                    )
                    _ = await StockMoveLine.create(
                        StockMoveLine(
                            move_line_id=new_id("mli"),
                            company_id=company_id,
                            move_id=move.move_id,
                            transfer_id=None,
                            warehouse_id=warehouse_id,
                            kind=StockMoveLineKind.COUNT,
                            product_id=product_id,
                            quantity=STOCK_ZERO,
                            done_quantity=STOCK_ZERO,
                            location_id=bin_loc.location_id,
                            location_dest_id=bin_loc.location_id,
                            created_at=now,
                        )
                    )
                    report.lines_created += 1
            return LaneOutcome(result=report, events=[])

        _ = await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=f"cycle_count:{company_id}:{warehouse_id}:{new_id('cc')}",
            command_type="stock/maintenance/cycle_count",
            actor_user_id="system",
            result_type=CycleCountReport,
            body=body,
        )
        return report

    # --- Верхнеуровневые тики ---

    async def reconcile_tick(self) -> dict[str, int]:
        """Полная сверка по всем компаниям — один прогон тика."""
        async with traced_operation(
            "stock.maintenance.reconcile",
            operation_category="maintenance",
        ):
            total_fixed = 0
            total_closed = 0
            for company_id in await self.list_company_ids():
                for wh in await self._warehouses(company_id):
                    report = await self.reconcile_warehouse(
                        company_id=company_id, warehouse_id=wh.warehouse_id
                    )
                    total_fixed += report.reserved_fixed
                    total_closed += report.moves_closed
            return {"reserved_fixed": total_fixed, "moves_closed": total_closed}

    async def claims_gc_tick(self) -> dict[str, int]:
        async with traced_operation(
            "stock.maintenance.claims_gc",
            operation_category="maintenance",
        ):
            cutoff = utcnow() - DEFAULT_CLAIM_TTL
            released = 0
            for company_id in await self.list_company_ids():
                for wh in await self._warehouses(company_id):
                    report = await self.release_stale_claims(
                        company_id=company_id,
                        warehouse_id=wh.warehouse_id,
                        claimed_before=cutoff,
                    )
                    released += report.released
            return {"released": released}

    async def reorder_tick(self) -> dict[str, int]:
        async with traced_operation(
            "stock.maintenance.reorder",
            operation_category="maintenance",
        ):
            created = 0
            for company_id in await self.list_company_ids():
                created += await self.reorder_company(company_id=company_id)
            return {"created": created}

    async def cycle_count_tick(self) -> dict[str, int]:
        async with traced_operation(
            "stock.maintenance.cycle_count",
            operation_category="maintenance",
        ):
            due = utcnow() - DEFAULT_CYCLE_COUNT_INTERVAL
            bins = 0
            lines = 0
            for company_id in await self.list_company_ids():
                for wh in await self._warehouses(company_id):
                    report = await self.cycle_count_warehouse(
                        company_id=company_id,
                        warehouse_id=wh.warehouse_id,
                        due_before=due,
                    )
                    bins += report.bins_scheduled
                    lines += report.lines_created
            return {"bins_scheduled": bins, "lines_created": lines}

    # --- Lane event relay / GC ---

    async def relay_tick(self) -> dict[str, int]:
        """Догнать lane-коммиты, чей быстрый путь до bus не дошёл.

        ``publish_lane_run`` публикует сразу после коммита; если процесс
        умер между коммитом и публикацией — событие «зависло»: остаток
        изменился, а UI об этом не узнал. Тик дочитывает такие коммиты
        и допубликовывает их — повтор безопасен, push идемпотентен.
        """
        async with traced_operation(
            "stock.maintenance.lane_relay",
            operation_category="maintenance",
        ):
            from core.lanes.publish import relay_cutoff, relay_lane_commits

            published = await relay_lane_commits(
                using=STOCK_DB, created_before=relay_cutoff(), limit=200
            )
            return {"relayed": published}

    async def lane_gc_tick(self) -> dict[str, int]:
        """Вымести опубликованные lane-коммиты за окном идемпотентности."""
        async with traced_operation(
            "stock.maintenance.lane_gc",
            operation_category="maintenance",
        ):
            from core.lanes.publish import expire_cutoff, expire_lane_commits

            expired = await expire_lane_commits(
                using=STOCK_DB, published_before=expire_cutoff()
            )
            return {"expired": expired}


__all__ = [
    "CYCLE_COUNT_BINS_PER_TICK",
    "ClaimsGcReport",
    "CycleCountReport",
    "DEFAULT_CLAIM_TTL",
    "DEFAULT_CYCLE_COUNT_INTERVAL",
    "MaintenanceService",
    "ReconcileReport",
]

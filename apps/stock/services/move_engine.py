"""`StockMoveEngine` — оркестратор жизненного цикла складской накладной.

Каждая команда — это одно бизнес-действие над документом: зарегистрировать,
принять в работу, разложить резерв по ячейкам, исполнить (провести),
отменить, вернуть. Сервис отвечает за «документный оборот» склада.

Устройство одной команды:
  1. Вне транзакции — читаем план: существуют ли склад/тип операции,
     решаем putaway (куда ставить приход — может звать ИИ-рефлекс).
  2. Внутри одной ``run_in_lanes`` транзакции — ``*_in_lane`` метод
     модели делает всю работу: статусы, строки резерва, изменения
     quant'ов, слои оценки.
  3. После commit — ``publish_lane_run`` публикует события, накопленные
     в LaneCommit (``stock/move/done``, ``stock/quant/changed`` …).

Прямой publish событий из сервиса запрещён — события едут только из
LaneCommit после коммита: «уведомление = факт зафиксирован в БД».
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from apps.stock.models import (
    ReflexMode,
    ReservationPolicy,
    StockDecision,
    StockLocation,
    StockLocationUsage,
    StockMove,
    StockMoveState,
    StockOperationType,
    StockQuant,
    StockTransfer,
    StockTransferState,
    StockWarehouse,
)
from apps.stock.models.common import STOCK_DB, StockMoveSpec
from apps.stock.models.enums import STOCK_QUANT_USAGES, StockRemovalStrategy
from apps.stock.services.placement_service import PlacementService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import LaneRun, publish_lane_run
from core.request_scope import command_idempotency_key
from core.tracing.attributes import ATTR_TENANT_COMPANY_ID
from core.tracing.operation_span import traced_operation
from core.types import OtelAttributeValue


class StockMoveEngine:
    """Жизненный цикл transfer/move: confirm → assign → done, cancel, return."""

    def __init__(self, placement: PlacementService) -> None:
        self._placement: PlacementService = placement


    def _span(self, name: str, *, company_id: str, warehouse_id: str | None, resource_id: str | None = None, extra: dict[str, OtelAttributeValue] | None = None):
        """Span мутации склада: компания/склад/документ как атрибуты."""
        merged: dict[str, OtelAttributeValue] = {ATTR_TENANT_COMPANY_ID: company_id}
        if warehouse_id is not None:
            merged["stock.warehouse_id"] = warehouse_id
        if extra:
            merged.update(extra)
        return traced_operation(
            name,
            operation_category="stock_mutation",
            resource_type="stock_warehouse",
            resource_id=resource_id or warehouse_id,
            extra_attributes=merged,
        )

    # --- CRUD перевода ---

    async def create_transfer(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        operation_type_id: str,
        partner_entity_id: str | None,
        owner_entity_id: str | None,
        scheduled_at: datetime | None,
        origin_document_type: str | None,
        origin_document_id: str | None,
        barcode: str | None,
        moves: list[StockMoveSpec],
        priority: int = 0,
        date_deadline: datetime | None = None,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/transfers/create_requested",
    ) -> StockTransfer:
        """Регистрация накладной: шапка + строки черновиком.

        Бизнес-шаг «приняли заказ/поставку на склад»: документу даётся
        номер ``WH/IN/00042``, строки-движения (move) записываются со
        статусом draft. Локации по умолчанию берутся из типа операции
        (приёмка: поставщик → зона приёмки).
        """
        warehouse = await self._require_warehouse(company_id, warehouse_id)
        operation_type = await self._require_operation_type(
            company_id, operation_type_id
        )
        if operation_type.warehouse_id != warehouse.warehouse_id:
            raise PlatformConflictError(
                "Operation type belongs to another warehouse",
                error_code="operation_type_warehouse_mismatch",
            )
        resolved: list[StockMoveSpec] = []
        for spec in moves:
            src_id = spec.location_id or operation_type.default_source_location_id
            dst_id = spec.location_dest_id or operation_type.default_dest_location_id
            if src_id is None or dst_id is None:
                raise PlatformConflictError(
                    "Move requires location_id/location_dest_id",
                    error_code="move_locations_missing",
                )
            resolved.append(
                spec.model_copy(
                    update={"location_id": src_id, "location_dest_id": dst_id}
                )
            )
        name_prefix = (
            f"{warehouse.code}/{operation_type.code.value.upper()}"
        )
        async with self._span(
            "stock.transfer.create",
            company_id=company_id,
            warehouse_id=warehouse_id,
            extra={"stock.moves": len(moves)},
        ):
            run = await StockTransfer.create_in_lane(
                company_id=company_id,
                warehouse_id=warehouse_id,
                operation_type_id=operation_type_id,
                name_prefix=name_prefix,
                partner_entity_id=partner_entity_id,
                owner_entity_id=owner_entity_id,
                scheduled_at=scheduled_at,
                origin_document_type=origin_document_type,
                origin_document_id=origin_document_id,
                barcode=barcode,
                moves=resolved,
                priority=priority,
                date_deadline=date_deadline,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    # --- Жизненный цикл ---

    async def confirm_transfer(
        self,
        *,
        company_id: str,
        transfer_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/transfers/confirm_requested",
    ) -> StockTransfer:
        """Подтверждение накладной — «заказ принят в работу».

        Все строки → ``confirmed``. Если тип операции требует резерв
        сразу (``reservation_policy=at_confirm`` — например горячая
        отгрузка), тут же раскладываем остаток по ячейкам и решаем
        putaway.

        ``auto_validate`` на типе операции — режим микросклада «одна
        кнопка»: после подтверждения сами раскладываем резерв и, если
        документ полностью обеспечен (``assigned``), проводим его. При
        частичном резерве автопроводка НЕ включается — нехватку решает
        человек (иначе слепая доказка).
        """
        transfer = await self._require_transfer(company_id, transfer_id)
        operation_type = await self._require_operation_type(
            company_id, transfer.operation_type_id
        )
        reserve = operation_type.reservation_policy == ReservationPolicy.AT_CONFIRM
        dests: dict[str, str] = {}
        decisions: list[StockDecision] = []
        if reserve:
            dests, decisions = await self._resolve_dests(
                company_id, transfer, operation_type
            )
        async with self._span(
            "stock.transfer.confirm",
            company_id=company_id,
            warehouse_id=transfer.warehouse_id,
            resource_id=transfer_id,
        ):
            run = await StockTransfer.confirm_in_lane(
                company_id=company_id,
                transfer_id=transfer_id,
                reserve=reserve,
                dest_overrides=dests,
                decisions=decisions,
                removal_strategies=await self._resolve_strategies(
                    company_id, transfer
                ),
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        confirmed = run.result
        if operation_type.auto_validate:
            assigned = await self.assign_transfer(
                company_id=company_id,
                transfer_id=transfer_id,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
            )
            if assigned.state == StockTransferState.ASSIGNED:
                confirmed = await self.validate_transfer(
                    company_id=company_id,
                    transfer_id=transfer_id,
                    idempotency_key=idempotency_key,
                    actor_user_id=actor_user_id,
                    create_backorder=True,
                )
        return confirmed

    async def assign_transfer(
        self,
        *,
        company_id: str,
        transfer_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/transfers/assign_requested",
    ) -> StockTransfer:
        """Раскладка резерва — «под заказ зарезервированы единицы».

        По каждой строке: остатки источника → ``reserved_quantity``,
        строки исполнения с конкретными ячейками/партиями. После этого
        заказ «видит» свой товар на полках, другие документы его не
        заберут.
        """
        transfer = await self._require_transfer(company_id, transfer_id)
        operation_type = await self._require_operation_type(
            company_id, transfer.operation_type_id
        )
        dests, decisions = await self._resolve_dests(
            company_id, transfer, operation_type
        )
        async with self._span(
            "stock.transfer.assign",
            company_id=company_id,
            warehouse_id=transfer.warehouse_id,
            resource_id=transfer_id,
        ):
            run = await StockTransfer.assign_in_lane(
                company_id=company_id,
                transfer_id=transfer_id,
                dest_overrides=dests,
                decisions=decisions,
                removal_strategies=await self._resolve_strategies(
                    company_id, transfer
                ),
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def _resolve_dests(
        self,
        company_id: str,
        transfer: StockTransfer,
        operation_type: StockOperationType,
    ) -> tuple[dict[str, str], list[StockDecision]]:
        """Решение «куда ставить приход» до входа в транзакцию.

        Для строк приёмки (источник виртуальный — товар ещё не наш)
        спрашиваем putaway-рефлекс: он возвращает StockDecision с
        кандидатами ячеек и выбранной. Рефлекс может звать ИИ — поэтому
        работает вне lane; внутрь транзакции уходит уже готовое решение
        (пишется в stock_decisions для аудита, применяется к dst move).
        """
        warehouse = await self._require_warehouse(company_id, transfer.warehouse_id)
        moves = await StockMove.list_for_transfer(company_id, transfer.transfer_id)
        dests: dict[str, str] = {}
        decisions: list[StockDecision] = []
        for move in moves:
            if move.state in {
                StockMoveState.DONE,
                StockMoveState.CANCEL,
                StockMoveState.WAITING,
            }:
                continue
            if move.route_id is not None:
                # Плечо маршрута: приёмник задан шагом маршрута —
                # рукопожатие цепочки нельзя перебивать putaway-рефлексом.
                continue
            dst = await StockLocation.by_id(company_id, move.location_dest_id)
            src = await StockLocation.by_id(company_id, move.location_id)
            if (
                dst is None
                or src is None
                or dst.usage not in STOCK_QUANT_USAGES | {StockLocationUsage.VIEW}
                or src.usage in STOCK_QUANT_USAGES
            ):
                continue
            decision = await self._placement.resolve_putaway(
                company_id=company_id,
                warehouse=warehouse,
                operation_type=operation_type,
                move=move,
                owner_entity_id=transfer.owner_entity_id,
            )
            if decision is None:
                continue
            decisions.append(decision)
            if (
                decision.chosen_location_id is not None
                and operation_type.putaway_mode != ReflexMode.SHADOW
            ):
                dests[move.move_id] = decision.chosen_location_id
        return dests, decisions

    async def _resolve_strategies(
        self, company_id: str, transfer: StockTransfer
    ) -> dict[str, StockRemovalStrategy]:
        """Стратегия отбора по каждой открытой строке — до входа в lane.

        Чтение справочников (карточка товара → тип хранения зоны
        источника → дефолт склада) выполняется вне транзакции; внутрь
        полосы уходит готовая карта ``move_id → стратегия``.
        """
        moves = await StockMove.list_for_transfer(
            company_id, transfer.transfer_id
        )
        open_moves = [
            m
            for m in moves
            if m.state not in {StockMoveState.DONE, StockMoveState.CANCEL}
        ]
        return await self._placement.resolve_for_transfer(
            company_id=company_id, moves=open_moves
        )

    async def validate_transfer(
        self,
        *,
        company_id: str,
        transfer_id: str,
        create_backorder: bool = True,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/transfers/validate_requested",
        causation_id: str | None = None,
    ) -> StockTransfer:
        """Исполнение накладной — «подпись кладовщика под ордером».

        Все открытые строки проводятся (post_step): остатки quant'ов
        меняются, резерв снимается, проводки оценки пишутся в
        stock_value_layers, документ → done. Недовыполненный остаток —
        по политике backorder типа операции (``always``/``never``/
        ``ask`` через ``create_backorder``).
        """
        transfer = await self._require_transfer(company_id, transfer_id)
        operation_type = await self._require_operation_type(
            company_id, transfer.operation_type_id
        )
        dests, decisions = await self._resolve_dests(
            company_id, transfer, operation_type
        )
        async with self._span(
            "stock.transfer.validate",
            company_id=company_id,
            warehouse_id=transfer.warehouse_id,
            resource_id=transfer_id,
        ):
            run = await StockTransfer.validate_in_lane(
                company_id=company_id,
                transfer_id=transfer_id,
                reserve_dests=dests,
                decisions=decisions,
                removal_strategies=await self._resolve_strategies(
                    company_id, transfer
                ),
                backorder_policy=operation_type.backorder_policy,
                operation_code=operation_type.code.value,
                create_backorder=create_backorder,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
                causation_id=causation_id,
            )
        await publish_lane_run(run, using=STOCK_DB)
        await self.advance_chains(company_id, transfer.transfer_id)
        return run.result

    async def advance_chains(
        self, company_id: str, transfer_id: str
    ) -> None:
        """Продвинуть маршрутные цепочки документа после проводки.

        Смотрит done-строки с ``move_dest_id``: спящее следующее плечо
        (``waiting``) активируется в полосе своего склада — для
        межскладской цепочки это ДРУГАЯ полоса, поэтому активация
        идёт отдельным lane-run'ом после публикации исходного коммита
        (полосы не вложены друг в друга). Порядок строго «после
        publish»: пока исходная проводка не закоммичена, будить
        следующее плечо нельзя — товар ещё не на промежуточной точке.
        """
        moves = await StockMove.list_for_transfer(company_id, transfer_id)
        posted = {
            m.move_id for m in moves if m.state == StockMoveState.DONE
        }
        if not posted:
            return
        successors = [
            m
            for m in moves
            if m.state == StockMoveState.WAITING
            and m.move_origin_id in posted
        ]
        strategies = await self._placement.resolve_for_transfer(
            company_id=company_id, moves=successors
        )
        base_warehouse_id = (
            await self._require_transfer(company_id, transfer_id)
        ).warehouse_id
        for successor in successors:
            async with self._span(
                "stock.move.chain_activate",
                company_id=company_id,
                warehouse_id=successor.warehouse_id or base_warehouse_id,
                resource_id=successor.move_id,
            ):
                run = await StockMove.activate_in_lane(
                    company_id=company_id,
                    move_id=successor.move_id,
                    warehouse_id=successor.warehouse_id or base_warehouse_id,
                    removal_strategy=strategies.get(
                        successor.move_id, StockRemovalStrategy.FIFO
                    ),
                    idempotency_key=command_idempotency_key(
                        f"chain-activate:{successor.move_id}"
                    ),
                    actor_user_id="system",
                    command_type="stock/moves/activate_requested",
                )
            await publish_lane_run(run, using=STOCK_DB)

    async def cancel_transfer(
        self,
        *,
        company_id: str,
        transfer_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/transfers/cancel_requested",
    ) -> StockTransfer:
        """Аннулирование накладной до исполнения.

        Черновые и зарезервированные строки отменяются, резерв
        возвращается в доступное. Если хоть одна строка уже done —
        отмена запрещена: проведённое исправляется только возвратом.
        """
        transfer = await self._require_transfer(company_id, transfer_id)
        async with self._span(
            "stock.transfer.cancel",
            company_id=company_id,
            warehouse_id=transfer.warehouse_id,
            resource_id=transfer_id,
        ):
            run = await StockTransfer.cancel_in_lane(
                company_id=company_id,
                transfer_id=transfer_id,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def unreserve_move(
        self,
        *,
        company_id: str,
        move_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/moves/unreserve_requested",
    ) -> StockMove:
        """Снять резерв с одной строки — товар снова доступен другим.

        Сценарий «отложили заказ»: зарезервированные единицы
        освобождаются (reserved_quantity падает, строки резерва
        отменяются), move возвращается в confirmed — ждёт нового
        assign.
        """
        move = await StockMove.by_id(company_id, move_id)
        if move is None:
            raise PlatformNotFoundError(
                "Move not found", error_code="move_not_found"
            )
        if move.transfer_id is not None:
            run: LaneRun[StockTransfer] = (
                await StockTransfer.unreserve_move_in_lane(
                    company_id=company_id,
                    transfer_id=move.transfer_id,
                    move_id=move_id,
                    idempotency_key=command_idempotency_key(idempotency_key),
                    actor_user_id=actor_user_id,
                    command_type=command_type,
                )
            )
            await publish_lane_run(run, using=STOCK_DB)
        else:
            release = await StockMove.release_in_lane(
                company_id=company_id,
                move_id=move_id,
                warehouse_id=None,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
            await publish_lane_run(release, using=STOCK_DB)
        fresh = await StockMove.by_id(company_id, move_id)
        assert fresh is not None
        return fresh

    async def return_transfer(
        self,
        *,
        company_id: str,
        transfer_id: str,
        move_quantities: dict[str, Decimal] | None,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/transfers/return_requested",
        causation_id: str | None = None,
    ) -> StockTransfer:
        """Возврат товара — обратная накладная ``WH/OUT/…/RET/…``.

        Клиент вернул часть отгрузки или мы возвращаем поставщику —
        создаётся новый transfer ``return_of_id``, строки зеркальны
        (концы движения перевернуты). Проводится сразу: возврат — это
        факт, а не заявка. Оценка — по себестоимости исходного move.
        """
        source = await self._require_transfer(company_id, transfer_id)
        operation_type = await self._require_operation_type(
            company_id, source.operation_type_id
        )
        run = await StockTransfer.return_in_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            move_quantities=move_quantities,
            operation_code=operation_type.code.value,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
            causation_id=causation_id,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    # --- Инвентаризация ---

    async def inventory_set(
        self,
        *,
        company_id: str,
        quant_id: str,
        inventory_quantity: Decimal,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/quants/inventory_set_requested",
    ) -> StockQuant:
        """Шаг 1 инвентаризации: «насчитали на полке N шт» — черновик.

        Пишет ``inventory_quantity`` на строку остатка. Само число
        ничего не двигает — это зафиксированный факт подсчёта, а не
        движение. Расхождение станет движением на шаге ``inventory_apply``.
        """
        warehouse_id = await self._quant_warehouse_id(company_id, quant_id)
        async with self._span(
            "stock.quant.inventory_set",
            company_id=company_id,
            warehouse_id=warehouse_id,
            resource_id=quant_id,
        ):
            run = await StockQuant.update_inventory_quantity_in_lane(
                company_id=company_id,
                quant_id=quant_id,
                warehouse_id=warehouse_id,
                inventory_quantity=inventory_quantity,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def inventory_apply(
        self,
        *,
        company_id: str,
        quant_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/quants/inventory_apply_requested",
        causation_id: str | None = None,
    ) -> StockMove:
        """Шаг 2 инвентаризации: «утвердить расхождение» — проводка дельты.

        Дельта ``inventory_quantity − quantity`` превращается в
        проведённый StockMove через виртуальную локацию ``adjustment``:
        недостача — списание со склада (INVENTORY_LOSS в журнале
        стоимости), излишек — оприходование (INVENTORY_GAIN). Черновик
        подсчёта очищается.
        """
        warehouse_id = await self._quant_warehouse_id(company_id, quant_id)
        async with self._span(
            "stock.move.inventory_apply",
            company_id=company_id,
            warehouse_id=warehouse_id,
            resource_id=quant_id,
        ):
            run = await StockMove.apply_inventory_in_lane(
                company_id=company_id,
                quant_id=quant_id,
                warehouse_id=warehouse_id,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
                causation_id=causation_id,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    # --- helpers ---

    async def _quant_warehouse_id(
        self, company_id: str, quant_id: str
    ) -> str | None:
        quant = await StockQuant.by_id(company_id, quant_id)
        if quant is None:
            raise PlatformNotFoundError(
                "Quant not found", error_code="quant_not_found"
            )
        location = await StockLocation.by_id(company_id, quant.location_id)
        return location.warehouse_id if location is not None else None

    async def _require_warehouse(
        self, company_id: str, warehouse_id: str
    ) -> StockWarehouse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise PlatformNotFoundError(
                "Warehouse not found", error_code="warehouse_not_found"
            )
        return warehouse

    async def _require_operation_type(
        self, company_id: str, operation_type_id: str
    ) -> StockOperationType:
        operation_type = await StockOperationType.by_id(company_id, operation_type_id)
        if operation_type is None:
            raise PlatformNotFoundError(
                "Operation type not found", error_code="operation_type_not_found"
            )
        return operation_type

    async def _require_transfer(
        self, company_id: str, transfer_id: str
    ) -> StockTransfer:
        transfer = await StockTransfer.by_id(company_id, transfer_id)
        if transfer is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        return transfer

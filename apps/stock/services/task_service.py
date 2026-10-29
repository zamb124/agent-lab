"""TaskService — очередь складских заданий для операторов и техники.

StockMoveLine — это поручение («взять 6 шт из A-01»). Сервис отвечает
на вопрос «что делать прямо сейчас»:

* ``queue`` — открытые задания склада по приоритету/порядку обхода;
* ``next`` — первое задание, которое оператор способен исполнить
  на своей технике (ресурс фильтрует по типам хранения, ярусу,
  таре и «сыпучим» товарам);
* ``claim``/``release``/``assign`` — атомарный захват, возврат в
  очередь и раздача диспетчером; всё через полосу склада, push
  ``stock/move_line/assigned`` уходит после commit.

Способность ресурса решается чистой функцией ``line_fits_resource``
над уже прочитанными строками: тележка с ``max_level=2`` не получит
задание с четвёртого яруса, а кран без ``handles_loose`` — россыпь.
"""

from __future__ import annotations

from decimal import Decimal

from apps.stock.models import (
    StockLocation,
    StockMove,
    StockMoveLine,
    StockMoveLineClaimResult,
    StockMoveLineExceptionResult,
    StockMoveLineKind,
    StockResource,
    StockResourceType,
    StockTransfer,
)
from apps.stock.models.common import STOCK_DB
from core.errors.boundary import PlatformNotFoundError
from core.lanes import publish_lane_run
from core.request_scope import command_idempotency_key
from core.tracing.attributes import ATTR_TENANT_COMPANY_ID
from core.tracing.operation_span import traced_operation


def line_fits_resource(
    line: StockMoveLine,
    *,
    source_location: StockLocation | None,
    container: StockLocation | None,
    resource_type: StockResourceType,
) -> bool:
    """Чистая проверка «ресурс потянет это задание».

    Бизнес-смысл — допуск техники до работы: у каждого класса техники
    (``StockResourceType``) заданы рамки — какие типы хранения она
    обслуживает, до какого яруса достаёт, какую тару везёт и берёт ли
    россыпь. Задание «не по силам» просто не показывается оператору.

    Проверки (все должны пройти):
      * ярус исходной ячейки ≤ ``max_level`` ресурса;
      * ``storage_type`` ячейки входит в ``storage_type_ids``
        (пустой список = без ограничений);
      * задание по таре — тип контейнера ∈ ``allowed_container_type_ids``;
      * задание по россыпи — ресурс умеет ``handles_loose``.
    """
    if source_location is not None:
        if (
            resource_type.max_level is not None
            and source_location.level > resource_type.max_level
        ):
            return False
        if (
            resource_type.storage_type_ids
            and source_location.storage_type_id is not None
            and source_location.storage_type_id
            not in resource_type.storage_type_ids
        ):
            return False
    if line.kind == StockMoveLineKind.CONTAINER:
        allowed = resource_type.allowed_container_type_ids
        if allowed and (
            container is None
            or container.container_type_id not in allowed
        ):
            return False
    elif not resource_type.handles_loose:
        return False
    return True




def _mutation_span(name: str, *, company_id: str, warehouse_id: str, resource_id: str | None = None):
    """Span мутации заданий склада: компания/склад/строка — атрибуты."""
    return traced_operation(
        name,
        operation_category="stock_mutation",
        resource_type="stock_warehouse",
        resource_id=resource_id or warehouse_id,
        extra_attributes={
            ATTR_TENANT_COMPANY_ID: company_id,
            "stock.warehouse_id": warehouse_id,
        },
    )


class TaskService:
    """Очередь, захват и раздача заданий склада."""

    async def queue(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        assigned_user_id: str | None = None,
        zone_location_id: str | None = None,
        limit: int = 100,
    ) -> list[StockMoveLine]:
        """Открытая очередь склада (или «моя очередь» оператора)."""
        return await StockMoveLine.list_open_queue_by_priority_desc_stop_sequence_and_created_at(
            company_id,
            warehouse_id,
            assigned_user_id=assigned_user_id,
            zone_location_id=zone_location_id,
            limit=limit,
        )

    async def next_line(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        user_id: str,
        resource_id: str | None = None,
        zone_location_id: str | None = None,
        claim: bool = True,
    ) -> StockMoveLine | None:
        """Первое подходящее задание для оператора — и сразу захват.

        «Следующее задание» вычисляется как голова очереди, прошедшая
        фильтр возможностей ресурса. ``claim=True`` — стандартный ТСД-
        сценарий «дать работу»: задание закрепляется за оператором в
        той же полосе, чтобы два ТСД не забрали одно поручение.
        ``zone_location_id`` сужает выбор до поддерева зоны оператора.
        """
        lines = await StockMoveLine.list_open_queue_by_priority_desc_stop_sequence_and_created_at(
            company_id, warehouse_id, zone_location_id=zone_location_id,
            limit=200,
        )
        # Свободные или уже закреплённые за этим оператором — его
        # очередь; чужие задания не показываем.
        candidates = [
            line
            for line in lines
            if line.assigned_user_id in {None, user_id}
        ]
        if not candidates:
            return None
        resource_type: StockResourceType | None = None
        if resource_id is not None:
            resource = await StockResource.by_id(company_id, resource_id)
            if resource is None:
                raise PlatformNotFoundError(
                    "Resource not found", error_code="resource_not_found"
                )
            resource_type = await StockResourceType.by_id(
                company_id, resource.resource_type_id
            )
        if resource_type is None:
            chosen = candidates[0]
        else:
            locations = await StockLocation.found_in_company_by_ids(
                company_id,
                sorted(
                    {
                        loc_id
                        for line in candidates
                        for loc_id in (line.location_id, line.location_dest_id)
                    }
                    | {
                        line.container_id
                        for line in candidates
                        if line.container_id is not None
                    }
                ),
            )
            chosen = next(
                (
                    line
                    for line in candidates
                    if line_fits_resource(
                        line,
                        source_location=locations.get(line.location_id),
                        container=(
                            locations.get(line.container_id)
                            if line.container_id is not None
                            else None
                        ),
                        resource_type=resource_type,
                    )
                ),
                None,
            )
        if chosen is None or not claim:
            return chosen
        async with _mutation_span(
            "stock.move_line.claim",
            company_id=company_id,
            warehouse_id=warehouse_id,
        ):
            run = await StockMoveLine.claim_in_lane(
                company_id=company_id,
                warehouse_id=warehouse_id,
                move_line_ids=[chosen.move_line_id],
                user_id=user_id,
                resource_id=resource_id,
                claimed=True,
                idempotency_key=command_idempotency_key(None),
                actor_user_id=user_id,
                command_type="stock/move_lines/claim_requested",
            )
        await publish_lane_run(run, using=STOCK_DB)
        if chosen.assigned_user_id != user_id:
            chosen.assigned_user_id = user_id
            chosen.resource_id = resource_id
        return chosen

    async def claim(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        move_line_ids: list[str],
        user_id: str,
        resource_id: str | None = None,
        idempotency_key: str | None = None,
        command_type: str = "stock/move_lines/claim_requested",
    ) -> StockMoveLineClaimResult:
        """Оператор берёт задания сам — атомарный захват пакета."""
        async with _mutation_span(
            "stock.move_line.claim",
            company_id=company_id,
            warehouse_id=warehouse_id,
        ):
            run = await StockMoveLine.claim_in_lane(
                company_id=company_id,
                warehouse_id=warehouse_id,
                move_line_ids=move_line_ids,
                user_id=user_id,
                resource_id=resource_id,
                claimed=True,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def assign(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        move_line_ids: list[str],
        assignee_user_id: str,
        resource_id: str | None = None,
        actor_user_id: str,
        idempotency_key: str | None = None,
        command_type: str = "stock/move_lines/assign_requested",
    ) -> StockMoveLineClaimResult:
        """Диспетчер раздаёт задания — тот же захват, но ``claimed=False``."""
        async with _mutation_span(
            "stock.move_line.assign",
            company_id=company_id,
            warehouse_id=warehouse_id,
        ):
            run = await StockMoveLine.claim_in_lane(
                company_id=company_id,
                warehouse_id=warehouse_id,
                move_line_ids=move_line_ids,
                user_id=assignee_user_id,
                resource_id=resource_id,
                claimed=False,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def release(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        move_line_ids: list[str],
        user_id: str | None,
        actor_user_id: str,
        idempotency_key: str | None = None,
        command_type: str = "stock/move_lines/release_requested",
    ) -> StockMoveLineClaimResult:
        """Вернуть задания в очередь (свои — оператор, чужие — диспетчер)."""
        async with _mutation_span(
            "stock.move_line.release",
            company_id=company_id,
            warehouse_id=warehouse_id,
        ):
            run = await StockMoveLine.release_in_lane(
                company_id=company_id,
                warehouse_id=warehouse_id,
                move_line_ids=move_line_ids,
                user_id=user_id,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def update_move_line(
        self,
        *,
        company_id: str,
        move_line_id: str,
        done_quantity: Decimal | None,
        picked: bool | None,
        lot_id: str | None,
        location_dest_id: str | None,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/move_lines/update_requested",
    ) -> StockMoveLine:
        """Записать факт исполнения строки задания (скан оператора).

        ``done_quantity`` — сколько реально отсканировал кладовщик по
        этой строке (может отличаться от зарезервированного
        ``quantity``: не нашли товар, битая коробка). Именно сумма
        ``done_quantity`` строк станет фактическим движением при
        проводке накладной — это та цифра, по которой изменятся
        остатки и оценка.

        Правка идёт полосой склада (``update_line_in_lane``): два
        сканирования одной строки не перезапишут друг друга, событие
        обновления публикуется после коммита.
        """
        line = await StockMoveLine.by_id(company_id, move_line_id)
        if line is None:
            raise PlatformNotFoundError(
                "Move line not found", error_code="move_line_not_found"
            )
        warehouse_id = await self._line_warehouse_id(company_id, line)
        run = await StockMove.update_line_in_lane(
            company_id=company_id,
            warehouse_id=warehouse_id,
            move_line_id=move_line_id,
            done_quantity=done_quantity,
            picked=picked,
            lot_id=lot_id,
            location_dest_id=location_dest_id,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def _line_warehouse_id(
        self, company_id: str, line: StockMoveLine
    ) -> str | None:
        move = await StockMove.by_id(company_id, line.move_id)
        if move is None or move.transfer_id is None:
            return None
        transfer = await StockTransfer.by_id(company_id, move.transfer_id)
        return transfer.warehouse_id if transfer is not None else None

    async def report_exception(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        move_line_id: str,
        shortage: Decimal,
        reason: str,
        actor_user_id: str,
        idempotency_key: str | None = None,
        command_type: str = "stock/move_lines/report_exception_requested",
    ) -> StockMoveLineExceptionResult:
        """«Пришёл — а товара нет»: недостача/бой по строке задания.

        Одна транзакция: строка укорачивается на недостачу (требование
        уходит в перерезерв), резерв на ячейке отпускается, на ячейку
        ставится задание пересчёта. Push ``stock/move_line/exception``
        — точка подписки для эскалации (задача менеджеру в flows).
        """
        async with _mutation_span(
            "stock.move_line.exception",
            company_id=company_id,
            warehouse_id=warehouse_id,
            resource_id=move_line_id,
        ):
            run = await StockMoveLine.report_exception_in_lane(
                company_id=company_id,
                warehouse_id=warehouse_id,
                move_line_id=move_line_id,
                shortage=shortage,
                reason=reason,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

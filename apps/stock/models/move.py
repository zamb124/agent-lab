"""Книга складских ордеров (stock_moves + stock_move_lines).

StockMove — единственный механизм изменения количества на складе:
любое перемещение товара — приход от поставщика, отгрузка клиенту,
перекладка между ячейками, списание недостачи — это документ «из
локации A в локацию B». Нет записи «прибавь 5 на полку» — только
движение с двумя концами, как проводка с дебетом и кредитом.

Жизненный цикл документа (state):

    draft                  — черновик, ещё ничего не обещал
      │ confirm
      ▼
    confirmed              — заказ принят в работу, резерв ещё не разложен
      │ assign (reserve_step)
      ▼
    partially_available    — свободного остатка хватило частично
    assigned               — под документ зарезервировано всё количество
      │ validate (post_step)
      ▼
    done                   — исполнено: quant'ы и слои оценки записаны

    cancel — отмена из draft/confirmed/assigned (резерв снимается);
    waiting — спящее плечо маршрутной цепочки: ждёт проводки
              предыдущего плеча (``move_origin_id`` → done), затем
              активируется ``activate_in_lane`` → ``confirmed``.

Кто что меняет в таблицах (одна транзакция на команду):

    reserve_step  → пишет строки stock_move_lines (план раскладки по
                    ячейкам/партиям) и поднимает quant.reserved_quantity
    post_step     → по каждой строке меняет quant.quantity (источник −,
                    приёмник +), снимает reserved, пишет слои
                    stock_value_layers, строки помечаются done
    release_step  → возвращает reserved_quantity и отменяет строки
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from apps.stock.models.common import (
    MONEY_DB,
    QTY_DB,
    STOCK_DB,
    STOCK_ZERO,
    new_id,
    require_stock,
    stock_command_lane,
    stock_company_lane,
)
from apps.stock.models.container_type import StockContainerType
from apps.stock.models.enums import (
    STOCK_EXTERNAL_USAGES,
    STOCK_QUANT_USAGES,
    StockLocationUsage,
    StockMoveLineKind,
    StockMoveLineState,
    StockMoveState,
    StockRemovalStrategy,
    StockTracking,
)
from apps.stock.models.events import (
    STOCK_CONTAINER_MOVED,
    STOCK_MOVE_DONE,
    STOCK_QUANT_CHANGED,
    StockContainerMovedPayload,
    StockMoveDonePayload,
    StockQuantChangedPayload,
    company_event,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.lot import StockLot
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.product import StockProduct
from apps.stock.models.quant import StockQuant
from apps.stock.models.removal import (
    RemovalBin,
    container_exact_cover,
    order_candidates_by_strategy_asc,
)
from apps.stock.models.scan import ScanLineDraft
from apps.stock.models.storage_rules import (
    BinContent,
    PlacementItem,
    check_placement,
)
from apps.stock.models.storage_type import StockStorageType
from apps.stock.models.value_layer import StockValueLayer
from core.catalog.models import CatalogProduct
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.events.contract import PlatformEvent
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models.platform_model import PlatformModel
from core.pagination import CursorPage, decode_cursor, encode_cursor
from core.types import (
    JsonValue,
    SqlParameterValue,
    parse_json_object,
    require_json_object,
)
from core.utils.time import utcnow

_REMOVABLE_STATES = {StockMoveState.DRAFT, StockMoveState.CONFIRMED, StockMoveState.WAITING}
_RESERVABLE_STATES = {
    StockMoveState.CONFIRMED,
    StockMoveState.PARTIALLY_AVAILABLE,
    StockMoveState.ASSIGNED,
}

RESERVABLE_STATES = _RESERVABLE_STATES


@dataclass(frozen=True)
class PostedMove:
    """Исход `post_step`: состояние move после done + записанные строки/слои/quant."""

    move: StockMove
    done_now: bool
    done_qty: Decimal
    lines: list[StockMoveLine]
    layers: list[StockValueLayer]
    quants: list[StockQuant]
    src_usage: StockLocationUsage
    dst_usage: StockLocationUsage


def move_done_event(
    posted: PostedMove,
    *,
    company_id: str,
    warehouse_id: str | None,
    operation_code: str | None,
    actor_user_id: str,
    causation_id: str | None,
) -> PlatformEvent:
    """`stock/move/done` из состояния уже завершённого move (внутри tx коммита)."""
    move = posted.move
    total_value = sum((layer.value for layer in posted.layers), STOCK_ZERO)
    return company_event(
        STOCK_MOVE_DONE,
        StockMoveDonePayload(
            company_id=company_id,
            move_id=move.move_id,
            transfer_id=move.transfer_id,
            warehouse_id=warehouse_id,
            operation_type_id=move.operation_type_id,
            operation_code=operation_code,
            product_id=move.product_id,
            location_id=move.location_id,
            location_dest_id=move.location_dest_id,
            location_usage=posted.src_usage,
            location_dest_usage=posted.dst_usage,
            quantity=posted.done_qty,
            unit_price=move.unit_price,
            unit_cost=(
                abs(total_value / posted.done_qty)
                if posted.done_qty > STOCK_ZERO
                else None
            ),
            value=abs(total_value) if posted.layers else None,
            value_layer_ids=[layer.layer_id for layer in posted.layers],
            returned_move_id=move.returned_move_id,
            origin_document_type=move.origin_document_type,
            origin_document_id=move.origin_document_id,
            done_at=(move.done_at or utcnow()).isoformat(),
        ),
        company_id=company_id,
        actor_user_id=actor_user_id,
        causation_id=causation_id,
    )


def quant_changed_events(
    quants: Sequence[StockQuant],
    *,
    company_id: str,
    move_id: str | None,
    actor_user_id: str,
    causation_id: str | None,
) -> list[PlatformEvent]:
    """`stock/quant/changed` по затронутым quant (состояние уже после дельты)."""
    return [
        company_event(
            STOCK_QUANT_CHANGED,
            StockQuantChangedPayload(
                company_id=company_id,
                quant_id=quant.quant_id,
                product_id=quant.product_id,
                location_id=quant.location_id,
                lot_id=quant.lot_id,
                owner_entity_id=quant.owner_entity_id,
                quantity=quant.quantity,
                reserved_quantity=quant.reserved_quantity,
                move_id=move_id,
            ),
            company_id=company_id,
            actor_user_id=actor_user_id,
            causation_id=causation_id,
        )
        for quant in quants
    ]


class StockMove(PlatformModel):
    """Складской ордер «переместить N единиц товара из A в B». Таблица ``stock_moves``.

    Поля, как их читает бизнес:

    * ``product_qty`` / ``product_uom_qty`` / ``uom_id`` — потребность
      документа: сколько заказали (в единицах документа — например
      коробки) и сколько это в базовых единицах товара (штуках).
      Конвертация делается при создании перевода; движок работает только
      с ``product_qty``.
    * ``location_id`` / ``location_dest_id`` — «откуда взять» и «куда
      положить». Концы могут быть виртуальными (поставщик, клиент,
      локация инвентаризации): это границы, а не полки.
    * ``unit_price`` — цена из первичного документа (счёт поставщика);
      пишется в слой как ``price_source=document``. Вычисленная
      себестоимость отгрузки на move не хранится — она в StockValueLayer.
    * ``returned_move_id`` — если это возврат: какой move возвращаем
      (оценка возьмёт его себестоимость).
    * ``priority`` / ``date_deadline`` — срочность для планировщика волн
      и заданий (Фаза 4).
    * ``warehouse_id`` — склад исполнения (денормализация; определяет
      полосу сериализации и выдачу заданий операторам).

    Шаги движка (``confirm_step``/``reserve_step``/``post_step``/
    ``release_step``/``cancel_step``) не открывают ``atomic`` — они
    исполняются внутри транзакции полосы склада (``run_in_lanes`` в
    ``*_in_lane``-classmethod'ах), поэтому сериализованы по складу.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_moves"
        indexes: list[Index] = [
            Index(["company_id", "transfer_id"]),
            Index(["company_id", "product_id", "state"]),
            Index(["company_id", "location_id", "state"]),
            Index(["company_id", "location_dest_id", "state"]),
            Index(["company_id", "origin_document_id", "state"]),
            Index(["company_id", "move_origin_id"]),
        ]

    move_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    """Склад исполнения — денормализация для выдачи заданий и полос."""
    transfer_id: str | None = DbField(default=None, max_length=64)
    product_id: str = DbField(max_length=64)
    product_qty: Decimal = DbField(db_type=QTY_DB)
    """Спрос в ЕИ товара (после конвертации из `uom_id` при создании)."""
    product_uom_qty: Decimal = DbField(db_type=QTY_DB)
    """Спрос в ЕИ документа."""
    uom_id: str = DbField(max_length=64)
    location_id: str = DbField(max_length=64)
    location_dest_id: str = DbField(max_length=64)
    state: StockMoveState = DbField(default=StockMoveState.DRAFT)
    operation_type_id: str | None = DbField(default=None, max_length=64)
    origin_document_type: str | None = DbField(default=None, max_length=64)
    origin_document_id: str | None = DbField(default=None, max_length=64)
    returned_move_id: str | None = DbField(default=None, max_length=64)
    route_id: str | None = DbField(default=None, max_length=64)
    """Маршрут цепочки, если движение — плечо многошагового маршрута."""
    move_origin_id: str | None = DbField(default=None, max_length=64)
    """Предыдущее плечо цепочки (pull: это плечо ждёт его в waiting)."""
    move_dest_id: str | None = DbField(default=None, max_length=64)
    """Следующее плечо цепочки — активируется, когда это done."""
    unit_price: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    priority: int = DbField(default=0)
    date: datetime = DbField()
    date_deadline: datetime | None = DbField(default=None)
    done_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, move_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, move_id=move_id
        ).get_or_none()

    @classmethod
    async def by_id_locked(cls, company_id: str, move_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, move_id=move_id
        ).for_update().get_or_none()

    @classmethod
    async def require_locked(cls, company_id: str, move_id: str) -> Self:
        """Строка под FOR UPDATE внутри lane-транзакции; нет — `move_not_found`."""
        move = await cls.by_id_locked(company_id, move_id)
        if move is None:
            raise PlatformNotFoundError(
                "Move not found", error_code="move_not_found"
            )
        return move

    @classmethod
    async def list_for_transfer_by_created_at_asc(
        cls, company_id: str, transfer_id: str
    ) -> list[Self]:
        """Движения накладной, ORDER BY created_at ASC. Предела нет. Пустые поля не проверяются."""
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).order_by("created_at").all()

    @classmethod
    async def list_unordered_open_by_origin(
        cls,
        company_id: str,
        origin_document_type: str,
        origin_document_id: str,
    ) -> list[Self]:
        """Открытые движения документа-источника: draft, waiting, confirmed, partially_available, assigned. Порядка и предела нет. Пустые поля не проверяются. Пока такое движение есть, повторный заказ по тому же источнику не создаётся."""
        return await cls.objects.filter(
            company_id=company_id,
            origin_document_type=origin_document_type,
            origin_document_id=origin_document_id,
            state__in=[
                StockMoveState.DRAFT,
                StockMoveState.WAITING,
                StockMoveState.CONFIRMED,
                StockMoveState.PARTIALLY_AVAILABLE,
                StockMoveState.ASSIGNED,
            ],
        ).all()

    @classmethod
    async def list_unordered_confirmed_partial_or_assigned_for_warehouse(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Движения склада в confirmed, partially_available или assigned. Порядка и limit нет."""
        return await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            state__in=[
                StockMoveState.CONFIRMED,
                StockMoveState.PARTIALLY_AVAILABLE,
                StockMoveState.ASSIGNED,
            ],
        ).all()

    @classmethod
    async def list_page_by_created_at_desc(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None = None,
        location_ids: list[str] | None = None,
        product_id: str | None = None,
        state: StockMoveState | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CursorPage[StockMove]:
        """Страница движений компании, ORDER BY created_at DESC, move_id DESC.

        Keyset-курсор по ``(created_at, move_id)`` — повторяемая страница
        без сдвига при вставках сверху ленты. ``location_ids`` — движение
        с любым концом в этом наборе (источник ИЛИ приёмник); пустой
        список — пустая страница. ``warehouse_id``, ``product_id`` и
        ``state`` равные ``None`` не фильтруют. Невалидный ``cursor`` —
        ValueError.
        """
        if location_ids is not None and not location_ids:
            return CursorPage[StockMove](items=[], next_cursor=None, has_more=False)
        params: list[SqlParameterValue] = [company_id]
        where = ["company_id = $1"]

        def add(value: SqlParameterValue) -> str:
            params.append(value)
            return f"${len(params)}"

        if warehouse_id is not None:
            where.append(f"warehouse_id = {add(warehouse_id)}")
        if product_id is not None:
            where.append(f"product_id = {add(product_id)}")
        if state is not None:
            state_param = add(StockMoveState(state).value)
            where.append(f"state = {state_param}::stock_move_state_enum")
        if location_ids is not None:
            ids_params = ", ".join(add(location_id) for location_id in location_ids)
            where.append(
                f"(location_id IN ({ids_params}) OR location_dest_id IN ({ids_params}))"
            )
        if cursor is not None:
            cursor_ts, cursor_id = decode_cursor(cursor)
            ts_param = add(cursor_ts)
            id_param = add(cursor_id)
            where.append(f"(created_at, move_id) < ({ts_param}::timestamptz, {id_param})")
        limit_param = add(limit + 1)
        fetched = await execute_raw(
            "SELECT row_to_json(stock_moves) AS item FROM stock_moves WHERE "
            + " AND ".join(where)
            + f" ORDER BY created_at DESC, move_id DESC LIMIT {limit_param}",
            params,
            using=STOCK_DB,
        )
        parsed = [_stock_move_from_row(row) for row in fetched]
        has_more = len(parsed) > limit
        page = parsed[:limit]
        next_cursor: str | None = None
        if has_more and len(page) > 0:
            last = page[-1]
            next_cursor = encode_cursor(last.created_at, last.move_id)
        return CursorPage[StockMove](
            items=page, next_cursor=next_cursor, has_more=has_more
        )

    # --- Шаги движка внутри lane-транзакции (свой atomic не открывают) ---

    @classmethod
    async def confirm_step(cls, *, company_id: str, move: Self) -> Self:
        """Перевод ``draft → confirmed`` — «заказ принят в работу».

        Бизнес-смысл: документ зафиксирован, товар ещё не зарезервирован
        под конкретные ячейки, остатки не изменены. С этого момента
        документ виден кладовщикам как готовящийся к исполнению.
        Повторный confirm — no-op (идемпотентность); из других состояний
        — ``move_state_conflict``.
        """
        if move.state in {StockMoveState.CONFIRMED, StockMoveState.WAITING}:
            return move
        require_stock(
            move.state == StockMoveState.DRAFT,
            "Move cannot be confirmed from its state",
            error_code="move_state_conflict",
        )
        _ = await cls.objects.filter(
            company_id=company_id, move_id=move.move_id
        ).update(using=STOCK_DB, state=StockMoveState.CONFIRMED)
        move.state = StockMoveState.CONFIRMED
        return move

    @classmethod
    async def reserve_step(
        cls,
        *,
        company_id: str,
        move: Self,
        dest_location_id: str | None,
        owner_entity_id: str | None,
        removal_strategy: StockRemovalStrategy = StockRemovalStrategy.FIFO,
    ) -> Self:
        """Раскладка резерва — «из каких ячеек и партий берём товар».

        Бизнес-смысл резерва: мы обещаем документу конкретные физические
        единицы. Это видно на остатках: ``reserved_quantity`` растёт,
        ``available`` падает — другой заказ эти же единицы уже не заберёт.

        Что происходит в таблицах:

        * Источник внешний (поставщик на приходе, сурплюс
          инвентаризации — ``STOCK_EXTERNAL_USAGES``): резервировать
          нечего — чужой остаток не наш. Создаётся одна строка
          stock_move_lines на всё количество, состояние → ``assigned``.
        * Источник — наш склад (bin/container/transit) или зона ``view``:
          обходим quant'ы поддерева источника — ``view`` сам остатков
          не держит, но в поддерево входят все ячейки и контейнеры зоны
          (приём «откуда-то из зоны»). Порядок — стратегия отбора
          (``removal_strategy`` —
          FIFO/FEFO/LIFO/ближайшая/целая тара; решается сервисом до
          входа в полосу из цепочки «товар → тип хранения → склад»)
          и под каждый подходящий остаток пишем строку:
          ``line.quantity = взятое количество``, на quant —
          ``reserved_quantity += take``.

          Стратегия ``least_containers`` срабатывает особо: если вся
          потребность лежит на одном контейнере — создаём строку
          ``kind=container`` (отгружаем паллету целиком, товар внутри
          не расписываем).

        Итог: ``assigned`` (закрыто полностью) или ``partially_available``
        (части не хватило — недостающее количество при валидации уйдёт
        в backorder по политике документа).

        ``dest_location_id`` — решение putaway-рефлекса, принятое до
        входа в полосу (записано в stock_decisions); здесь просто
        применяем его к шапке move.
        """
        require_stock(
            move.state in _RESERVABLE_STATES,
            "Move cannot be reserved from its state",
            error_code="move_state_conflict",
        )
        if dest_location_id is not None:
            move.location_dest_id = dest_location_id
            _ = await cls.objects.filter(
                company_id=company_id, move_id=move.move_id
            ).update(using=STOCK_DB, location_dest_id=dest_location_id)
        src = await StockLocation.by_id(company_id, move.location_id)
        dst = await StockLocation.by_id(company_id, move.location_dest_id)
        if src is None or dst is None:
            raise PlatformNotFoundError(
                "Move location not found", error_code="location_not_found"
            )
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(company_id, move.move_id)
        reserved = sum((line.quantity for line in lines), STOCK_ZERO)
        needed = move.product_qty - reserved
        if needed <= STOCK_ZERO:
            await cls.write_state(company_id, move, StockMoveState.ASSIGNED)
            return move
        if src.usage in STOCK_EXTERNAL_USAGES:
            line = StockMoveLine(
                move_line_id=new_id("mli"),
                company_id=company_id,
                move_id=move.move_id,
                transfer_id=move.transfer_id,
                warehouse_id=move.warehouse_id,
                product_id=move.product_id,
                quantity=needed,
                done_quantity=needed,
                owner_entity_id=owner_entity_id,
                location_id=move.location_id,
                location_dest_id=move.location_dest_id,
                priority=move.priority,
                sequence=dst.pick_sequence,
                created_at=utcnow(),
            )
            _ = await StockMoveLine.objects.create(instance=line)
            await cls.write_state(company_id, move, StockMoveState.ASSIGNED)
            return move
        location_ids = await StockLocation.list_subtree_ids_by_parent_path_asc(
            company_id, move.location_id
        )
        candidates = await StockQuant.list_available_by_in_date_and_quant_id_asc_locked(
            company_id=company_id,
            product_id=move.product_id,
            location_ids=location_ids,
            owner_entity_id=owner_entity_id,
        )
        candidate_locations = await StockLocation.found_in_company_by_ids(
            company_id, [q.location_id for q in candidates]
        )
        removal_bins = {
            loc_id: RemovalBin(
                usage=loc.usage, pick_sequence=loc.pick_sequence
            )
            for loc_id, loc in candidate_locations.items()
        }
        candidates = order_candidates_by_strategy_asc(
            list(candidates),
            strategy=removal_strategy,
            needed=needed,
            locations=removal_bins,
        )
        if removal_strategy == StockRemovalStrategy.LEAST_CONTAINERS:
            covered = await cls._reserve_whole_container(
                company_id=company_id,
                move=move,
                ordered=candidates,
                needed=needed,
                locations=removal_bins,
                owner_entity_id=owner_entity_id,
            )
            if covered:
                return move
        remaining = needed
        for quant in candidates:
            if remaining <= STOCK_ZERO:
                break
            take = min(quant.available_quantity, remaining)
            line = StockMoveLine(
                move_line_id=new_id("mli"),
                company_id=company_id,
                move_id=move.move_id,
                transfer_id=move.transfer_id,
                warehouse_id=move.warehouse_id,
                product_id=move.product_id,
                lot_id=quant.lot_id,
                owner_entity_id=quant.owner_entity_id,
                quantity=take,
                done_quantity=take,
                location_id=quant.location_id,
                location_dest_id=move.location_dest_id,
                priority=move.priority,
                sequence=removal_bins[quant.location_id].pick_sequence,
                created_at=utcnow(),
            )
            _ = await StockMoveLine.objects.create(instance=line)
            quant.reserved_quantity += take
            quant.updated_at = utcnow()
            _ = await quant.save()
            remaining -= take
        state = (
            StockMoveState.ASSIGNED
            if remaining <= STOCK_ZERO
            else StockMoveState.PARTIALLY_AVAILABLE
        )
        await cls.write_state(company_id, move, state)
        return move

    @classmethod
    async def _reserve_whole_container(
        cls,
        *,
        company_id: str,
        move: Self,
        ordered: list[StockQuant],
        needed: Decimal,
        locations: dict[str, RemovalBin],
        owner_entity_id: str | None,
    ) -> bool:
        """Стратегия «минимум тары»: зарезервировать контейнер целиком.

        Обходим кандидатов в порядке отбора (контейнеры идут первыми,
        самый маленький достаточный — раньше). Для каждой контейнерной
        локации читаем ВСЕ остатки её поддерева под блокировкой и
        проверяем ``container_exact_cover``: содержимое однородно (наш
        товар, наш владелец), без чужих резервов и суммарно покрывает
        потребность. Отгружать «грязную» паллету значило бы молча
        выдать чужой товар под чужим резервом — такой контейнер
        пропускаем и идём к следующему.

        При успехе каждый остаток внутри резервируется целиком
        (``reserved_quantity = quantity``): тара уезжает со всем
        содержимым, «вытащить» часть под другой заказ нельзя. Пишется
        одна строка ``kind=container`` с ``quantity=0`` — масса
        задаётся фактическим содержимым на момент проводки.
        """
        for cand in ordered:
            meta = locations.get(cand.location_id)
            if meta is None or meta.usage != StockLocationUsage.CONTAINER:
                continue
            subtree = await StockLocation.list_subtree_ids_by_parent_path_asc(
                company_id, cand.location_id
            )
            inside = await StockQuant.list_unordered_for_locations(
                company_id, subtree, for_update=True
            )
            if (
                container_exact_cover(
                    inside,
                    product_id=move.product_id,
                    owner_entity_id=owner_entity_id,
                    needed=needed,
                )
                is None
            ):
                continue
            for quant in inside:
                if quant.quantity > STOCK_ZERO:
                    quant.reserved_quantity = quant.quantity
                    quant.updated_at = utcnow()
                    _ = await quant.save()
            line = StockMoveLine(
                move_line_id=new_id("mli"),
                company_id=company_id,
                move_id=move.move_id,
                transfer_id=move.transfer_id,
                warehouse_id=move.warehouse_id,
                product_id=move.product_id,
                kind=StockMoveLineKind.CONTAINER,
                container_id=cand.location_id,
                owner_entity_id=owner_entity_id,
                quantity=STOCK_ZERO,
                done_quantity=STOCK_ZERO,
                location_id=cand.location_id,
                location_dest_id=move.location_dest_id,
                priority=move.priority,
                sequence=meta.pick_sequence,
                created_at=utcnow(),
            )
            _ = await StockMoveLine.objects.create(instance=line)
            await cls.write_state(company_id, move, StockMoveState.ASSIGNED)
            return True
        return False

    @classmethod
    async def write_state(
        cls, company_id: str, move: Self, state: StockMoveState
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, move_id=move.move_id
        ).update(
            using=STOCK_DB,
            state=state,
            location_dest_id=move.location_dest_id,
        )
        move.state = state

    @classmethod
    async def release_step(cls, *, company_id: str, move: Self) -> Self:
        """Снятие резерва — «отказались от обещания, отпускаем товар».

        По каждой строке резерва: ``quant.reserved_quantity -=
        line.quantity`` — товар снова доступен другим заказам. Строки
        переводятся в ``cancelled`` (не удаляются физически — история
        «что обещали и не отдали» сохраняется).

        Строки с виртуального источника (поставщик) quant-резерва не
        создавали — их просто отменяем. ``reservation_underflow`` —
        защита от двойного снятия: reserved не может уйти в минус.
        """
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(company_id, move.move_id)
        location_ids = sorted({line.location_id for line in lines})
        locations = await StockLocation.found_in_company_by_ids(company_id, location_ids)
        for line in lines:
            if line.kind == StockMoveLineKind.CONTAINER:
                if line.state != StockMoveLineState.OPEN:
                    continue
                # Резерв по таре лежал на ВСЕХ остатках контейнера
                # целиком (reserved = quantity — полный лок стратегии
                # least_containers). Отпускаем ровно этот лок: quant
                # того же товара/владельца, залоченный «под крышку».
                # Чужой резерв (частичный или другого товара, появившийся
                # позже) не трогаем — обещание другого документа не наше.
                if line.container_id is None:
                    continue
                subtree = await StockLocation.list_subtree_ids_by_parent_path_asc(
                    company_id, line.container_id
                )
                for quant in await StockQuant.list_unordered_for_locations(
                    company_id, subtree, for_update=True
                ):
                    if (
                        quant.product_id == line.product_id
                        and quant.owner_entity_id == line.owner_entity_id
                        and quant.reserved_quantity == quant.quantity
                        and quant.reserved_quantity > STOCK_ZERO
                    ):
                        quant.reserved_quantity = STOCK_ZERO
                        quant.updated_at = utcnow()
                        _ = await quant.save()
                continue
            if line.quantity <= STOCK_ZERO or line.kind != StockMoveLineKind.QUANTITY:
                continue
            location = locations.get(line.location_id)
            if location is None:
                raise PlatformNotFoundError(
                    "Move line location not found", error_code="location_not_found"
                )
            if location.usage not in STOCK_QUANT_USAGES:
                continue
            quant = await StockQuant.by_key_locked(
                company_id=company_id,
                product_id=line.product_id,
                location_id=line.location_id,
                lot_id=line.lot_id,
                owner_entity_id=line.owner_entity_id,
            )
            if quant is None:
                raise PlatformConflictError(
                    "Reserved quant row is missing",
                    error_code="reservation_state_invalid",
                )
            quant.reserved_quantity -= line.quantity
            if quant.reserved_quantity < STOCK_ZERO:
                raise PlatformConflictError(
                    "Reservation underflow on release",
                    error_code="reservation_underflow",
                )
            quant.updated_at = utcnow()
            _ = await quant.save()
        _ = await StockMoveLine.objects.filter(
            company_id=company_id,
            move_id=move.move_id,
            state=StockMoveLineState.OPEN,
        ).update(using=STOCK_DB, state=StockMoveLineState.CANCELLED)
        return move

    @classmethod
    async def cancel_step(cls, *, company_id: str, move: Self) -> Self:
        """Отмена документа до исполнения — «ордер порвали».

        Если был резерв — сначала release_step (товар возвращается в
        доступное), затем state → ``cancel``. Остатки quant.quantity не
        тронуты: физически ничего не двигалось. Из ``done`` отменить
        нельзя — проведённое движение исправляется только обратным
        документом (return_), как в бухучёте.
        """
        require_stock(
            move.state in _REMOVABLE_STATES | _RESERVABLE_STATES,
            "Move cannot be cancelled from its state",
            error_code="move_state_conflict",
        )
        if move.state in _RESERVABLE_STATES:
            _ = await cls.release_step(company_id=company_id, move=move)
        _ = await cls.objects.filter(
            company_id=company_id, move_id=move.move_id
        ).update(using=STOCK_DB, state=StockMoveState.CANCEL)
        move.state = StockMoveState.CANCEL
        return move

    @classmethod
    async def post_step(
        cls,
        *,
        company_id: str,
        move: Self,
        warehouse_id: str | None,
        owner_entity_id: str | None,
        reserve_dest: str | None = None,
        removal_strategy: StockRemovalStrategy = StockRemovalStrategy.FIFO,
        actor_user_id: str | None = None,
    ) -> PostedMove:
        """Проведение документа — момент, когда остатки реально меняются.

        Это «подпись кладовщика под ордером»: до post_step весь резерв —
        лишь обещание; после — физическая правда в stock_quants и
        проводки в stock_value_layers, всё в одной транзакции.

        По каждой строке исполнения (``line.done_quantity`` — сколько
        реально отсканировали/приняли; ``line.quantity`` — сколько было
        зарезервировано):

        * Источник оцениваемый (bin/container/transit):
          ``quantity -= done`` и ``reserved -= quantity`` — сначала
          отпускаем обещание, потом списываем товар. Перед записью
          проверки: ``insufficient_stock`` (ушло бы в минус без
          allow_negative) и ``reservation_underflow`` (двойное списание
          резерва). Порядок важен: проверяем ДО записи, а не откатываем
          после.
        * Приёмник оцениваемый: ``quantity += done``; подбор строки по
          ключу (product, location, lot, owner) — та же партия/владелец
          дополняет существующую строку остатка.
        * ``kind=container``: товар внутри контейнера не трогаем —
          переезжает сама локация-контейнер со всем содержимым
          (``_post_container_line``).
        * Контроль перед приёмом: ``_check_tracking`` (serial/lot
          инварианты), ``_check_placement`` (правила storage_type
          ячейки: смешивание, ёмкость, контейнерность).

        После строк — ``write_for_done_move``: слои стоимости по
        матрице оценки (см. valuation.py). Внутреннее перемещение
        (bin→bin) слоёв не пишет — деньги не менялись.

        Пример. Заказ на 8 шт, строка-источник quantity=10 reserved=8:
          после done: quantity=6, reserved=0 (заказ исполнен полностью).
        Частично отдали 5 из 8: done_quantity=5 → quantity=5, reserved=3
        (остаток резерва ждёт backorder).
        """
        if move.state == StockMoveState.DONE:
            lines = await StockMoveLine.list_for_move_by_created_at_asc(
                company_id, move.move_id
            )
            layers = await StockValueLayer.objects.filter(
                company_id=company_id, move_id=move.move_id
            ).all()
            src = await StockLocation.by_id(company_id, move.location_id)
            dst = await StockLocation.by_id(company_id, move.location_dest_id)
            return PostedMove(
                move=move,
                done_now=False,
                done_qty=sum(
                    (line.done_quantity for line in lines), STOCK_ZERO
                ),
                lines=lines,
                layers=layers,
                quants=[],
                src_usage=(
                    src.usage if src is not None else StockLocationUsage.VIEW
                ),
                dst_usage=(
                    dst.usage if dst is not None else StockLocationUsage.VIEW
                ),
            )
        require_stock(
            move.state in _RESERVABLE_STATES,
            "Move cannot be completed from its state",
            error_code="move_state_conflict",
        )
        src = await StockLocation.by_id(company_id, move.location_id)
        dst = await StockLocation.by_id(company_id, move.location_dest_id)
        if src is None or dst is None:
            raise PlatformNotFoundError(
                "Move location not found", error_code="location_not_found"
            )
        product = await StockProduct.by_id(company_id, move.product_id)
        if product is None:
            raise PlatformNotFoundError(
                "Product not found", error_code="product_not_found"
            )
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(company_id, move.move_id)
        posting = [
            line for line in lines if line.kind != StockMoveLineKind.COUNT
        ]
        if not posting:
            _ = await cls.reserve_step(
                company_id=company_id,
                move=move,
                dest_location_id=reserve_dest,
                owner_entity_id=owner_entity_id,
                removal_strategy=removal_strategy,
            )
            lines = await StockMoveLine.list_open_for_move_by_created_at_asc(company_id, move.move_id)
            posting = [
                line for line in lines if line.kind != StockMoveLineKind.COUNT
            ]
        location_ids = sorted(
            {move.location_id, move.location_dest_id}
            | {line.location_id for line in posting}
            | {line.location_dest_id for line in posting}
            | {
                line.container_id
                for line in posting
                if line.container_id is not None
            }
        )
        locations = await StockLocation.found_in_company_by_ids(company_id, location_ids)
        storage_type_ids = sorted(
            {
                loc.storage_type_id
                for loc in locations.values()
                if loc.storage_type_id is not None
            }
        )
        storage_types = await StockStorageType.found_in_company_by_ids(company_id, storage_type_ids)
        ordered = sorted(
            posting,
            key=lambda line: (
                line.location_id,
                line.lot_id or "",
                line.owner_entity_id or "",
                line.move_line_id,
            ),
        )
        done_total = STOCK_ZERO
        touched: dict[str, StockQuant] = {}
        posted_line_ids: list[str] = []
        for line in ordered:
            line_src = locations.get(line.location_id)
            line_dst = locations.get(line.location_dest_id)
            if line_src is None or line_dst is None:
                raise PlatformNotFoundError(
                    "Move line location not found", error_code="location_not_found"
                )
            if line.kind == StockMoveLineKind.CONTAINER:
                moved_qty, container_quants = await cls._post_container_line(
                    company_id=company_id,
                    line=line,
                    move_dst=dst,
                    line_dst=line_dst,
                    locations=locations,
                    storage_types=storage_types,
                )
                done_total += moved_qty
                for quant in container_quants:
                    touched[quant.quant_id] = quant
                posted_line_ids.append(line.move_line_id)
                continue
            qty = await cls._post_quantity_line(
                company_id=company_id,
                move=move,
                move_src=src,
                move_dst=dst,
                line=line,
                line_src=line_src,
                line_dst=line_dst,
                product=product,
                storage_types=storage_types,
                touched=touched,
            )
            done_total += qty
            posted_line_ids.append(line.move_line_id)
        layers = await StockValueLayer.write_for_done_move(
            company_id=company_id,
            move_id=move.move_id,
            transfer_id=move.transfer_id,
            product_id=move.product_id,
            returned_move_id=move.returned_move_id,
            unit_price=move.unit_price,
            location_id=move.location_id,
            location_dest_id=move.location_dest_id,
            origin_document_type=move.origin_document_type,
            origin_document_id=move.origin_document_id,
            done_qty=done_total,
            valuation_method=product.valuation_method,
            standard_price=product.standard_price,
            src_usage=src.usage,
            dst_usage=dst.usage,
            src_partner_role=src.partner_role,
            owner_entity_id=owner_entity_id,
            warehouse_id=warehouse_id,
            layer_id_factory=lambda: new_id("svl"),
            consumption_id_factory=lambda: new_id("svc"),
        )
        now = utcnow()
        await StockMoveLine.mark_done(
            company_id,
            posted_line_ids,
            done_at=now,
            done_by_user_id=actor_user_id,
        )
        wave_ids = sorted(
            {
                line.wave_id
                for line in ordered
                if line.wave_id is not None
            }
        )
        if wave_ids:
            from apps.stock.models.wave import StockWave

            for wave_id in wave_ids:
                await StockWave.mark_done_when_no_open_lines(company_id, wave_id)
        _ = await cls.objects.filter(
            company_id=company_id, move_id=move.move_id
        ).update(using=STOCK_DB, state=StockMoveState.DONE, done_at=now)
        move.state = StockMoveState.DONE
        move.done_at = now
        return PostedMove(
            move=move,
            done_now=True,
            done_qty=done_total,
            lines=ordered,
            layers=layers,
            quants=list(touched.values()),
            src_usage=src.usage,
            dst_usage=dst.usage,
        )

    @classmethod
    async def post_lines_in_lane(
        cls,
        *,
        company_id: str,
        move_id: str,
        warehouse_id: str | None,
        drafts: list[ScanLineDraft],
        container_move: tuple[str, str] | None,
        owner_entity_id: str | None,
        operation_code: str | None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
        causation_id: str | None = None,
        on_move_done: Callable[..., Awaitable[PlatformEvent | None]] | None = None,
    ) -> LaneRun[StockMove]:
        """Атомарная скан-проводка: «набрал на ТСД — записал факт».

        Одна транзакция в полосе склада делает всё сразу:

        1. Черновые строки контекста материализуются в move-строки:
           отсканированное количество «откусывается» от открытых
           резервных строк (сплит: ``quantity -= scanned`` у исходной,
           новая строка quantity=scanned/done=scanned — резерв падает
           ровно на проведённое); лишнее/незапланированное — отдельной
           строкой ``quantity=0, done=scanned`` (переотгрузка фактом).
        2. Каждая новая строка проводится ``_post_quantity_line``/
           ``_post_container_line`` — остатки, резервы, правила ячеек.
        3. Слои оценки пишутся по сумме этого коммита
           (``done_total``) — несколько коммитов по одному move
           дают сумму, равную итоговой проводке.
        4. Если открытых строк не осталось — move → ``done``; иначе
           остаётся в работе до следующего коммита или validate.

        ``container_move=(container_id, dest_id)`` — ветка «перевезти
        паллету»: одна строка ``kind=container``, масса = содержимое
        на момент проводки.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[StockMove]:
            move = await cls.objects.filter(
                company_id=company_id, move_id=move_id
            ).for_update().get_or_none()
            if move is None:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            require_stock(
                move.state in _RESERVABLE_STATES,
                "Move cannot take scan commit from its state",
                error_code="move_state_conflict",
            )
            src = await StockLocation.by_id(company_id, move.location_id)
            dst = await StockLocation.by_id(company_id, move.location_dest_id)
            if src is None or dst is None:
                raise PlatformNotFoundError(
                    "Move location not found", error_code="location_not_found"
                )
            product = await StockProduct.by_id(company_id, move.product_id)
            if product is None:
                raise PlatformNotFoundError(
                    "Product not found", error_code="product_not_found"
                )
            open_lines = await StockMoveLine.list_open_for_move_by_created_at_asc(
                company_id, move.move_id
            )
            # Локации концов черновиков грузим разом — нужны и для
            # ``sequence`` (pick_sequence рабочей ячейки), и для
            # проводки строк ниже.
            endpoint_ids = {
                move.location_id,
                move.location_dest_id,
                *(
                    value
                    for draft in drafts
                    for value in (
                        draft.location_id,
                        draft.location_dest_id,
                        draft.container_id,
                    )
                    if value is not None
                ),
                *(container_move or ()),
            }
            endpoint_locations = await StockLocation.found_in_company_by_ids(
                company_id, sorted(endpoint_ids)
            )

            def _seq_of(location_id: str) -> int:
                loc = endpoint_locations.get(location_id)
                return loc.pick_sequence if loc is not None else 0

            now = utcnow()
            new_lines: list[StockMoveLine] = []
            consumed_line_ids: list[str] = []

            async def add_line(
                *,
                kind: StockMoveLineKind,
                location_id: str,
                location_dest_id: str,
                quantity: Decimal,
                done_quantity: Decimal,
                lot_id: str | None = None,
                container_id: str | None = None,
                owner: str | None = None,
                wave_id: str | None = None,
                sequence: int = 0,
                stop_order: int = 0,
            ) -> StockMoveLine:
                line = StockMoveLine(
                    move_line_id=new_id("mli"),
                    company_id=company_id,
                    move_id=move.move_id,
                    transfer_id=move.transfer_id,
                    warehouse_id=move.warehouse_id,
                    product_id=move.product_id,
                    kind=kind,
                    lot_id=lot_id,
                    container_id=container_id,
                    owner_entity_id=owner if owner is not None else owner_entity_id,
                    quantity=quantity,
                    done_quantity=done_quantity,
                    location_id=location_id,
                    location_dest_id=location_dest_id,
                    priority=move.priority,
                    wave_id=wave_id,
                    sequence=sequence,
                    stop_order=stop_order,
                    created_at=now,
                )
                _ = await StockMoveLine.objects.create(instance=line)
                new_lines.append(line)
                return line

            for draft in drafts:
                if draft.container_id is None and draft.quantity <= STOCK_ZERO:
                    raise PlatformConflictError(
                        "Scan line draft quantity must be positive",
                        error_code="done_quantity_invalid",
                    )
                if draft.product_id != move.product_id:
                    # Оператор отсканировал чужой товар: молча провести
                    # его как товар накладной — фальсификация факта
                    # движения. Отклоняем всю пачку до проводки.
                    raise PlatformConflictError(
                        "Scan line product does not match the move product",
                        error_code="scan_product_mismatch",
                    )
                src_id = draft.location_id or move.location_id
                dst_id = draft.location_dest_id or move.location_dest_id
                if draft.container_id is not None:
                    _ = await add_line(
                        kind=StockMoveLineKind.CONTAINER,
                        container_id=draft.container_id,
                        lot_id=draft.lot_id,
                        quantity=STOCK_ZERO,
                        done_quantity=STOCK_ZERO,
                        location_id=draft.container_id,
                        location_dest_id=dst_id,
                        sequence=_seq_of(draft.container_id),
                    )
                    continue
                remaining = draft.quantity
                # Сплит открытых резервных строк по месту/партии.
                for cand in open_lines:
                    if remaining <= STOCK_ZERO:
                        break
                    if (
                        cand.kind != StockMoveLineKind.QUANTITY
                        or cand.location_id != src_id
                        or cand.location_dest_id != dst_id
                        or cand.quantity <= STOCK_ZERO
                    ):
                        continue
                    if draft.lot_id is not None and cand.lot_id != draft.lot_id:
                        continue
                    take = min(cand.quantity, remaining)
                    _ = await StockMoveLine.objects.filter(
                        company_id=company_id,
                        move_line_id=cand.move_line_id,
                    ).update(using=STOCK_DB, quantity=cand.quantity - take)
                    cand.quantity -= take
                    if cand.quantity <= STOCK_ZERO:
                        # Резерв строки отобран целиком в исполненную —
                        # пустая оболочка закрывается, иначе move не
                        # увидит «всё сделано» и не станет done.
                        consumed_line_ids.append(cand.move_line_id)
                    _ = await add_line(
                        kind=StockMoveLineKind.QUANTITY,
                        lot_id=cand.lot_id,
                        quantity=take,
                        done_quantity=take,
                        location_id=src_id,
                        location_dest_id=dst_id,
                        owner=cand.owner_entity_id,
                        wave_id=cand.wave_id,
                        sequence=cand.sequence,
                        stop_order=cand.stop_order,
                    )
                    remaining -= take
                if remaining > STOCK_ZERO:
                    # Скан сверх резерва — факт без обещания.
                    _ = await add_line(
                        kind=StockMoveLineKind.QUANTITY,
                        lot_id=draft.lot_id,
                        quantity=STOCK_ZERO,
                        done_quantity=remaining,
                        location_id=src_id,
                        location_dest_id=dst_id,
                        sequence=_seq_of(src_id),
                    )

            if container_move is not None:
                container_id, dest_id = container_move
                _ = await add_line(
                    kind=StockMoveLineKind.CONTAINER,
                    container_id=container_id,
                    quantity=STOCK_ZERO,
                    done_quantity=STOCK_ZERO,
                    location_id=container_id,
                    location_dest_id=dest_id,
                    sequence=_seq_of(container_id),
                )

            if not new_lines:
                raise PlatformConflictError(
                    "Scan commit has nothing to post",
                    error_code="scan_nothing_to_commit",
                )

            locations = endpoint_locations
            storage_types = await StockStorageType.found_in_company_by_ids(
                company_id,
                sorted(
                    {
                        loc.storage_type_id
                        for loc in locations.values()
                        if loc.storage_type_id is not None
                    }
                ),
            )
            done_total = STOCK_ZERO
            touched: dict[str, StockQuant] = {}
            posted_ids: list[str] = []
            for line in new_lines:
                line_src = locations.get(line.location_id)
                line_dst = locations.get(line.location_dest_id)
                if line_src is None or line_dst is None:
                    raise PlatformNotFoundError(
                        "Move line location not found",
                        error_code="location_not_found",
                    )
                if line.kind == StockMoveLineKind.CONTAINER:
                    moved_qty, container_quants = await cls._post_container_line(
                        company_id=company_id,
                        line=line,
                        move_dst=dst,
                        line_dst=line_dst,
                        locations=locations,
                        storage_types=storage_types,
                    )
                    done_total += moved_qty
                    for quant in container_quants:
                        touched[quant.quant_id] = quant
                else:
                    done_total += await cls._post_quantity_line(
                        company_id=company_id,
                        move=move,
                        move_src=src,
                        move_dst=dst,
                        line=line,
                        line_src=line_src,
                        line_dst=line_dst,
                        product=product,
                        storage_types=storage_types,
                        touched=touched,
                    )
                posted_ids.append(line.move_line_id)

            layers = await StockValueLayer.write_for_done_move(
                company_id=company_id,
                move_id=move.move_id,
                transfer_id=move.transfer_id,
                product_id=move.product_id,
                returned_move_id=move.returned_move_id,
                unit_price=move.unit_price,
                location_id=move.location_id,
                location_dest_id=move.location_dest_id,
                origin_document_type=move.origin_document_type,
                origin_document_id=move.origin_document_id,
                done_qty=done_total,
                valuation_method=product.valuation_method,
                standard_price=product.standard_price,
                src_usage=src.usage,
                dst_usage=dst.usage,
                src_partner_role=src.partner_role,
                owner_entity_id=owner_entity_id,
                warehouse_id=warehouse_id,
                layer_id_factory=lambda: new_id("svl"),
                consumption_id_factory=lambda: new_id("svc"),
            )
            await StockMoveLine.mark_done(
                company_id,
                posted_ids + consumed_line_ids,
                done_at=now,
                done_by_user_id=actor_user_id,
            )
            wave_ids = sorted(
                {
                    line.wave_id
                    for line in new_lines
                    if line.wave_id is not None
                }
            )
            if wave_ids:
                from apps.stock.models.wave import StockWave

                for wave_id in wave_ids:
                    await StockWave.mark_done_when_no_open_lines(company_id, wave_id)
            still_open = [
                line
                for line in await StockMoveLine.list_open_for_move_by_created_at_asc(
                    company_id, move.move_id
                )
                if line.kind != StockMoveLineKind.COUNT
            ]
            events: list[PlatformEvent] = quant_changed_events(
                list(touched.values()),
                company_id=company_id,
                move_id=move.move_id,
                actor_user_id=actor_user_id,
                causation_id=causation_id,
            )
            if not still_open:
                _ = await cls.objects.filter(
                    company_id=company_id, move_id=move.move_id
                ).update(
                    using=STOCK_DB,
                    state=StockMoveState.DONE,
                    done_at=now,
                )
                move.state = StockMoveState.DONE
                move.done_at = now
                posted = PostedMove(
                    move=move,
                    done_now=True,
                    done_qty=done_total,
                    lines=new_lines,
                    layers=layers,
                    quants=list(touched.values()),
                    src_usage=src.usage,
                    dst_usage=dst.usage,
                )
                events.append(
                    move_done_event(
                        posted,
                        company_id=company_id,
                        warehouse_id=warehouse_id,
                        operation_code=operation_code,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                    )
                )
                if move.transfer_id is not None and on_move_done is not None:
                    # Накладная — проекция своих строк: move закрылся
                    # скан-коммитом → вызывающий пересчитывает состояние
                    # документа в той же транзакции (хук внедряется,
                    # чтобы move не импортировал StockTransfer — цикл).
                    transfer_done = await on_move_done(
                        company_id=company_id,
                        move=move,
                        operation_code=operation_code,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                        done_at=now,
                    )
                    if transfer_done is not None:
                        events.append(transfer_done)
            return LaneOutcome(result=move, events=events)

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            command_type=command_type,
            result_type=StockMove,
            body=body,
        )

    @classmethod
    async def _post_quantity_line(
        cls,
        *,
        company_id: str,
        move: Self,
        move_src: StockLocation,
        move_dst: StockLocation,
        line: StockMoveLine,
        line_src: StockLocation,
        line_dst: StockLocation,
        product: StockProduct,
        storage_types: dict[str, StockStorageType],
        touched: dict[str, StockQuant],
    ) -> Decimal:
        """Проводка одной строки количества — математика остатков.

        ``done`` — фактически исполненное (скан), ``quantity`` — резерв,
        который эта строка погашает. Порядок важен и не меняется:

        * источник: ``quantity -= done``, ``reserved -= quantity``
          (сначала отпускаем обещание, потом списываем товар);
        * приёмник: ``quantity += done`` по тому же ключу
          (product × cell × lot × owner); правила ячейки проверяются
          до записи — ``_check_placement``;
        * serial-товар: строка > 1 шт — отказ (см. ``_check_tracking``).

        ``view``-локация на любом конце строки — ошибка: зона не хранит
        остатков, проводка «в зону» теряла бы товар без записи quant'а,
        «из зоны» — создавала бы его из ниоткуда. Концы строки должны
        быть конкретными quant-локациями или внешними
        (``STOCK_EXTERNAL_USAGES``).

        Класс направления строки обязан совпадать с классом концов
        move (внешний ↔ внутренний): строка ``src=adjustment`` на
        внутреннем движении напечатала бы товар без INBOUND-проводки,
        ``dst=partner`` — уничтожила бы без OUTBOUND (оценка
        классифицируется по концам MOVE, а не строки).

        Возвращает проведённое количество для ``done_total`` move.
        """
        if (
            line_src.usage == StockLocationUsage.VIEW
            or line_dst.usage == StockLocationUsage.VIEW
        ):
            raise PlatformConflictError(
                "Move line endpoint cannot be a view location",
                error_code="location_usage_invalid",
            )
        if (
            (line_src.usage in STOCK_EXTERNAL_USAGES)
            != (move_src.usage in STOCK_EXTERNAL_USAGES)
            or (line_dst.usage in STOCK_EXTERNAL_USAGES)
            != (move_dst.usage in STOCK_EXTERNAL_USAGES)
        ):
            raise PlatformConflictError(
                "Move line endpoint crosses the move's internal/external boundary",
                error_code="location_usage_invalid",
            )
        qty = line.done_quantity
        if qty > STOCK_ZERO:
            await cls._check_tracking(
                company_id,
                product,
                line.lot_id,
                qty,
                line_src,
                line_dst,
            )
        if line_src.usage in STOCK_QUANT_USAGES:
            src_quant = await StockQuant.ensure_locked(
                company_id=company_id,
                product_id=move.product_id,
                location_id=line.location_id,
                lot_id=line.lot_id,
                owner_entity_id=line.owner_entity_id,
                warehouse_id=line_src.warehouse_id,
                quant_id=new_id("qnt"),
            )
            new_quantity = src_quant.quantity - qty
            new_reserved = src_quant.reserved_quantity - line.quantity
            if new_quantity < STOCK_ZERO and not line_src.allow_negative:
                raise PlatformConflictError(
                    "Insufficient stock on source location",
                    error_code="insufficient_stock",
                )
            if new_reserved < STOCK_ZERO:
                raise PlatformConflictError(
                    "Reservation underflow on done",
                    error_code="reservation_underflow",
                )
            src_quant.quantity = new_quantity
            src_quant.reserved_quantity = new_reserved
            src_quant.updated_at = utcnow()
            _ = await src_quant.save()
            touched[src_quant.quant_id] = src_quant
        if line_dst.usage in STOCK_QUANT_USAGES and qty > STOCK_ZERO:
            if product.tracking != StockTracking.SERIAL:
                await cls._check_placement(
                    company_id=company_id,
                    line=line,
                    line_dst=line_dst,
                    storage_types=storage_types,
                )
            removal_at = await cls._lot_removal_at(company_id, line.lot_id)
            dst_quant = await StockQuant.ensure_locked(
                company_id=company_id,
                product_id=move.product_id,
                location_id=line.location_dest_id,
                lot_id=line.lot_id,
                owner_entity_id=line.owner_entity_id,
                warehouse_id=line_dst.warehouse_id,
                removal_at=removal_at,
                quant_id=new_id("qnt"),
            )
            dst_quant.quantity += qty
            if removal_at is not None and (
                dst_quant.removal_at is None
                or removal_at < dst_quant.removal_at
            ):
                dst_quant.removal_at = removal_at
            dst_quant.updated_at = utcnow()
            _ = await dst_quant.save()
            touched[dst_quant.quant_id] = dst_quant
        return qty

    @classmethod
    async def _post_container_line(
        cls,
        *,
        company_id: str,
        line: StockMoveLine,
        move_dst: StockLocation,
        line_dst: StockLocation,
        locations: dict[str, StockLocation],
        storage_types: dict[str, StockStorageType],
    ) -> tuple[Decimal, list[StockQuant]]:
        """Строка «переместить контейнер» — переезжает паллета целиком.

        Контейнер — это локация ``usage=container`` (паллета, короб,
        тоут). Вместо перемещения каждой единицы товара отдельно мы
        переподчиняем контейнер новому родителю (``parent_id`` +
        ``parent_path`` поддерева) — его quant'ы «переезжают» вместе с
        ним без единой записи остатков. Плюс обновляем денормализованный
        ``warehouse_id`` у quant'ов поддерева, если контейнер уехал на
        другой склад.

        Резерв и остатки внутри:

        * приёмник — наш запас (bin/container/transit): содержимое
          едет как есть, а резерв, поставленный стратегией
          ``least_containers`` (``reserved = quantity`` на всех
          quant'ах внутри), гасится — обещание исполнено;
        * приёмник — «вне мира запаса» (partner/adjustment): товар
          покидает наш леджер — все остатки внутри обнуляются
          (quantity=0, reserved=0), а их сумма возвращается как
          done-количество строки для проводки оценки. Содержимое
          обязано быть однородным (товар строки, её владелец) —
          смешанную паллету молча выдать нельзя
          (``container_mixed_contents``).

        Возвращает ``(done-количество, затронутые quant'ы)`` —
        количество идёт в ``done_total`` move (проводка стоимости по
        факту содержимого), quant'ы — в события ``quant/changed``.
        """
        if line.container_id is None:
            raise PlatformConflictError(
                "Container line requires container_id",
                error_code="container_missing",
            )
        container = locations.get(line.container_id)
        if container is None:
            raise PlatformNotFoundError(
                "Container not found", error_code="container_not_found"
            )
        # Контейнер должен жить в том же складе, в полосе которого мы
        # сериализованы: иначе постинг мутирует quant'ы чужого склада,
        # не удерживая его lane (гонки двух складов).
        if (
            line.warehouse_id is not None
            and container.warehouse_id != line.warehouse_id
        ):
            raise PlatformConflictError(
                "Container belongs to another warehouse",
                error_code="container_warehouse_mismatch",
            )
        if (
            line_dst.usage in STOCK_QUANT_USAGES
            and line.warehouse_id is not None
            and line_dst.warehouse_id != line.warehouse_id
        ):
            raise PlatformConflictError(
                "Container destination belongs to another warehouse",
                error_code="container_warehouse_mismatch",
            )
        # Приёмник строки-контейнера держит класс направления move:
        # внутреннему движению — внутренний dst, отгрузке — внешний.
        # Иначе «переместить короб» на внутреннем документе уничтожило
        # бы товар без проводки списания.
        if (line_dst.usage in STOCK_EXTERNAL_USAGES) != (
            move_dst.usage in STOCK_EXTERNAL_USAGES
        ):
            raise PlatformConflictError(
                "Container destination crosses the move's internal/external boundary",
                error_code="location_usage_invalid",
            )
        await cls._validate_container_move(
            company_id=company_id, container=container, dest=line_dst
        )
        await cls._check_placement(
            company_id=company_id,
            line=line,
            line_dst=line_dst,
            storage_types=storage_types,
            placing_container_type_id=container.container_type_id,
        )
        subtree_ids = await StockLocation.list_subtree_ids_by_parent_path_asc(
            company_id, container.location_id
        )
        inside = await StockQuant.list_unordered_for_locations(
            company_id, subtree_ids, for_update=True
        )
        moved = STOCK_ZERO
        touched: list[StockQuant] = []
        outbound = line_dst.usage not in STOCK_QUANT_USAGES
        if outbound and any(
            q.quantity > STOCK_ZERO
            and (
                q.product_id != line.product_id
                or q.owner_entity_id != line.owner_entity_id
            )
            for q in inside
        ):
            raise PlatformConflictError(
                "Container holds goods beyond this move's product/owner",
                error_code="container_mixed_contents",
            )
        for quant in inside:
            if outbound:
                moved += quant.quantity
                quant.quantity = STOCK_ZERO
                quant.reserved_quantity = STOCK_ZERO
            else:
                if quant.product_id == line.product_id:
                    moved += quant.quantity
                # Отпускаем только НАШ полный лок (reserved == quantity
                # — сигнатура резерва least_containers). Чужой резерв
                # едет вместе с контейнером: товар физически на месте,
                # обещание другого документа остаётся в силе.
                if (
                    quant.product_id == line.product_id
                    and quant.owner_entity_id == line.owner_entity_id
                    and quant.reserved_quantity == quant.quantity
                    and quant.reserved_quantity > STOCK_ZERO
                ):
                    quant.reserved_quantity = STOCK_ZERO
                else:
                    continue
            quant.updated_at = utcnow()
            _ = await quant.save()
            touched.append(quant)
        _ = await StockLocation.rebind_subtree(
            company_id=company_id,
            root=container,
            new_parent=line_dst,
            new_warehouse_id=line_dst.warehouse_id,
        )
        await StockQuant.rebind_warehouse(
            company_id, subtree_ids, line_dst.warehouse_id
        )
        if line_dst.usage == StockLocationUsage.PARTNER:
            await cls._archive_disposable_container(company_id, container)
        return moved, touched

    @classmethod
    async def _validate_container_move(
        cls,
        *,
        company_id: str,
        container: StockLocation,
        dest: StockLocation,
    ) -> None:
        """Можно ли физически поставить этот контейнер в указанное место.

        Проверки (все — ``PlatformConflictError`` со своим error_code):

        * контейнер ли это вообще (``container_not_container``);
        * приёмник — bin/container/partner/transit: контейнер нельзя
          ставить в «вид» (view — это зона-агрегат, не полка)
          (``container_destination_invalid``);
        * нельзя вложить контейнер сам в себя или в своего потомка —
          ``parent_path`` цели не должен начинаться с пути контейнера
          (``container_cycle``);
        * тип контейнера разрешён в типе родителя
          (``allowed_parent_type_ids``: напр. «тоут нельзя ставить в
          короб») (``container_parent_denied``).
        """
        if container.usage != StockLocationUsage.CONTAINER:
            raise PlatformConflictError(
                "Location is not a container", error_code="container_not_container"
            )
        if dest.usage not in {
            StockLocationUsage.BIN,
            StockLocationUsage.CONTAINER,
            StockLocationUsage.PARTNER,
            StockLocationUsage.TRANSIT,
        }:
            raise PlatformConflictError(
                "Container destination must be bin/container/partner/transit",
                error_code="container_destination_invalid",
            )
        if dest.parent_path.startswith(container.parent_path):
            raise PlatformConflictError(
                "Cannot move a container inside its own subtree",
                error_code="container_cycle",
            )
        if (
            dest.usage == StockLocationUsage.CONTAINER
            and container.container_type_id is not None
        ):
            container_type = await StockContainerType.by_id(
                company_id, container.container_type_id
            )
            if (
                container_type is not None
                and container_type.allowed_parent_type_ids
                and dest.container_type_id
                not in container_type.allowed_parent_type_ids
            ):
                raise PlatformConflictError(
                    "Container type is not allowed inside this parent",
                    error_code="container_parent_denied",
                )

    @classmethod
    async def _archive_disposable_container(
        cls, company_id: str, container: StockLocation
    ) -> None:
        """Одноразовый контейнер после отгрузки «выбывает из оборота».

        Мешок/стрейч-паллета с ``is_reusable=false`` после доставки
        партнёру не возвращается — помечаем ``is_active=false``, чтобы
        он исчез из списков выбора и не копил «мёртвые» контейнеры в
        топологии. Содержимое уже ушло к партнёру вместе с ним.
        """
        if container.container_type_id is None:
            return
        container_type = await StockContainerType.by_id(
            company_id, container.container_type_id
        )
        if container_type is None or container_type.is_reusable:
            return
        _ = await StockLocation.objects.filter(
            company_id=company_id, location_id=container.location_id
        ).update(using=STOCK_DB, is_active=False)
        container.is_active = False

    @classmethod
    async def _check_placement(
        cls,
        *,
        company_id: str,
        line: StockMoveLine,
        line_dst: StockLocation,
        storage_types: dict[str, StockStorageType],
        placing_container_type_id: str | None = None,
    ) -> None:
        """Финальная проверка «можно ли положить сюда» в момент коммита.

        Планировщик мог предложить ячейку минуту назад — пока шла
        команда, кто-то мог её занять или заблокировать. Здесь —
        перепроверка по факту: блокировка приёмки
        (``location_putaway_blocked``) и правила типа хранения
        (``storage_rules.check_placement``: только контейнеры/россыпь,
        типы контейнеров, лимит контейнеров, смешивание товаров и
        партий, вес/объём). Нарушение — ``PlatformConflictError`` с
        кодом вида ``storage_*``.
        """
        violation = await cls._placement_violation(
            company_id=company_id,
            line_dst=line_dst,
            storage_types=storage_types,
            product_ids=frozenset({line.product_id} if line.product_id else set()),
            lot_ids=frozenset({line.lot_id} if line.lot_id else set()),
            placing_container_type_id=placing_container_type_id,
        )
        if violation is not None:
            raise PlatformConflictError(
                f"Placement denied by storage type: {violation}",
                error_code=violation,
            )

    @classmethod
    async def _placement_violation(
        cls,
        *,
        company_id: str,
        line_dst: StockLocation,
        storage_types: dict[str, StockStorageType],
        product_ids: frozenset[str],
        lot_ids: frozenset[str],
        placing_container_type_id: str | None,
    ) -> str | None:
        """Чистая проверка размещения в ``line_dst``: error_code или None.

        Собирает «картину ячейки» для чистых правил: какие товары и
        партии уже лежат (quant'ы), сколько контейнеров стоит внутри,
        есть ли россыпь — и спрашивает у ``check_placement``, впишется
        ли туда наш груз.
        """
        storage_type = (
            storage_types.get(line_dst.storage_type_id)
            if line_dst.storage_type_id is not None
            else None
        )
        if line_dst.putaway_blocked:
            return "location_putaway_blocked"
        if storage_type is None:
            return None
        contents = await StockQuant.list_unordered_for_locations(
            company_id, [line_dst.location_id]
        )
        child_containers = await StockLocation.objects.filter(
            company_id=company_id,
            parent_id=line_dst.location_id,
            usage=StockLocationUsage.CONTAINER,
            is_active=True,
        ).all()
        existing_products = {
            quant.product_id for quant in contents if quant.quantity > STOCK_ZERO
        }
        existing_lots = {
            quant.lot_id for quant in contents if quant.quantity > STOCK_ZERO and quant.lot_id
        }
        container_type = (
            await StockContainerType.by_id(company_id, placing_container_type_id)
            if placing_container_type_id is not None
            else None
        )
        return check_placement(
            storage_type=storage_type,
            placing=PlacementItem(
                product_ids=frozenset(existing_products | product_ids),
                lot_ids=frozenset(existing_lots | lot_ids),
                container_type_id=placing_container_type_id,
                total_weight=container_type.max_weight if container_type else None,
                total_volume=container_type.max_volume if container_type else None,
            ),
            existing=BinContent(
                product_ids=frozenset(existing_products),
                lot_ids=frozenset(existing_lots),
                container_type_ids=frozenset(
                    c.container_type_id
                    for c in child_containers
                    if c.container_type_id
                ),
                container_count=len(child_containers),
                has_loose=bool(existing_products),
                total_weight=STOCK_ZERO,
                total_volume=STOCK_ZERO,
            ),
        )

    @classmethod
    async def move_container_in_lane(
        cls,
        *,
        company_id: str,
        container_id: str,
        dest_location_id: str,
        actor_user_id: str,
        idempotency_key: str,
        command_type: str,
    ) -> LaneRun[StockLocation]:
        """Команда оператора «перевезти контейнер» вне документа-перевода.

        Скан по ТСД: оператор подъехал к паллете и перенёс её в другую
        ячейку — без заказа. Тот же rebind поддерева, что у строки
        ``kind=container`` (валидация + смена parent + rebind quant'ов),
        но как самостоятельная команда.

        Полосы берутся по складам обеих сторон: если контейнер едет
        на другой склад, команда сериализована сразу двумя полосами —
        ни одна сторона не увидит «запас в двух местах».
        """
        container0 = await StockLocation.by_id(company_id, container_id)
        dest0 = await StockLocation.by_id(company_id, dest_location_id)
        lanes = sorted(
            {
                stock_command_lane(company_id, loc.warehouse_id)
                for loc in (container0, dest0)
                if loc is not None
            }
        ) or [stock_company_lane(company_id)]

        async def body(_scope: LaneScope) -> LaneOutcome[StockLocation]:
            container = await StockLocation.objects.filter(
                company_id=company_id, location_id=container_id
            ).for_update().get_or_none()
            if container is None:
                raise PlatformNotFoundError(
                    "Container not found", error_code="container_not_found"
                )
            dest = await StockLocation.objects.filter(
                company_id=company_id, location_id=dest_location_id
            ).for_update().get_or_none()
            if dest is None:
                raise PlatformNotFoundError(
                    "Move location not found", error_code="location_not_found"
                )
            await cls._validate_container_move(
                company_id=company_id, container=container, dest=dest
            )
            storage_types = await StockStorageType.found_in_company_by_ids(
                company_id, [dest.storage_type_id] if dest.storage_type_id else []
            )
            subtree_ids = await StockLocation.list_subtree_ids_by_parent_path_asc(
                company_id, container.location_id
            )
            subtree_quants = await StockQuant.list_unordered_for_locations(
                company_id, subtree_ids, for_update=True
            )
            if dest.usage not in STOCK_QUANT_USAGES and any(
                q.quantity > STOCK_ZERO for q in subtree_quants
            ):
                # Непустой контейнер «за границу запаса» (партнёру,
                # на списание) увозит товар мимо леджера — только
                # через документ со строкой ``kind=container``.
                raise PlatformConflictError(
                    "Non-empty container can leave stock only via a transfer",
                    error_code="container_not_empty",
                )
            violation = await cls._placement_violation(
                company_id=company_id,
                line_dst=dest,
                storage_types=storage_types,
                product_ids=frozenset(
                    q.product_id for q in subtree_quants if q.quantity > STOCK_ZERO
                ),
                lot_ids=frozenset(
                    q.lot_id
                    for q in subtree_quants
                    if q.quantity > STOCK_ZERO and q.lot_id
                ),
                placing_container_type_id=container.container_type_id,
            )
            if violation is not None:
                raise PlatformConflictError(
                    f"Placement denied by storage type: {violation}",
                    error_code=violation,
                )
            from_parent_id = container.parent_id
            _ = await StockLocation.rebind_subtree(
                company_id=company_id,
                root=container,
                new_parent=dest,
                new_warehouse_id=dest.warehouse_id,
            )
            await StockQuant.rebind_warehouse(
                company_id, subtree_ids, dest.warehouse_id
            )
            if dest.usage == StockLocationUsage.PARTNER:
                await cls._archive_disposable_container(company_id, container)
            event = company_event(
                STOCK_CONTAINER_MOVED,
                StockContainerMovedPayload(
                    company_id=company_id,
                    container_id=container.location_id,
                    container_type_id=container.container_type_id,
                    from_parent_id=from_parent_id,
                    to_parent_id=dest.location_id,
                    warehouse_id=dest.warehouse_id,
                    moved_at=utcnow().isoformat(),
                ),
                company_id=company_id,
                actor_user_id=actor_user_id,
            )
            container.parent_id = dest.location_id
            container.warehouse_id = dest.warehouse_id
            return LaneOutcome(result=container, events=[event])

        return await run_in_lanes(
            lanes,
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=StockLocation,
            body=body,
        )

    @classmethod
    async def _lot_removal_at(
        cls, company_id: str, lot_id: str | None
    ) -> datetime | None:
        if lot_id is None:
            return None
        lot = await StockLot.by_id(company_id, lot_id)
        return lot.removal_at if lot is not None else None

    @classmethod
    async def _check_tracking(
        cls,
        company_id: str,
        product: StockProduct,
        lot_id: str | None,
        qty: Decimal,
        line_src: StockLocation,
        line_dst: StockLocation,
    ) -> None:
        """Проверки учёта по партиям и серийным номерам.

        Бизнес-правила трекинга (карточка товара, ``tracking``):

        * ``none`` — товар без партиёвки: строка с ``lot_id`` —
          ``lot_not_allowed» (нельзя «привязать» партию к тому, что её
          не имеет);
        * ``lot``/``serial`` — обязательно указывать партию/серийник на
          любом конце, который хранит остаток (``lot_required»): без
          номера мы не сможем ответить «какой именно сертификат ушёл»;
        * указанная партия/серийник обязаны существовать в справочнике
          и принадлежать этому товару — иначе ``lot_not_found`` /
          ``lot_product_mismatch``: фантомный номер на quant'е
          разрушил бы прослеживаемость («какой сертификат ушёл»);
        * ``serial`` — движение строго по одной штуке (qty ∈ {0, 1}),
          ``serial_quantity_invalid``: серийник — это физическая
          единица, половину серийника отгрузить нельзя. Плюс проверка
          инварианта «суммарный остаток по серийнику ≤ 1» — один и тот
          же серийник не может лежать на складе дважды.
        """
        tracking = product.tracking
        if tracking == StockTracking.NONE and lot_id is not None:
            raise PlatformConflictError(
                "Lot is not allowed for untracked product",
                error_code="lot_not_allowed",
            )
        if tracking != StockTracking.NONE and lot_id is None:
            if (
                line_src.usage in STOCK_QUANT_USAGES
                or line_dst.usage in STOCK_QUANT_USAGES
            ):
                raise PlatformConflictError(
                    "Lot is required for tracked product",
                    error_code="lot_required",
                )
        if tracking != StockTracking.NONE and lot_id is not None:
            lot = await StockLot.by_id_locked(company_id, lot_id)
            if lot is None:
                raise PlatformNotFoundError(
                    "Lot not found", error_code="lot_not_found"
                )
            if lot.product_id != product.product_id:
                raise PlatformConflictError(
                    "Lot belongs to another product",
                    error_code="lot_product_mismatch",
                )
        if tracking != StockTracking.SERIAL:
            return
        if qty not in {STOCK_ZERO, Decimal("1")}:
            raise PlatformConflictError(
                "Serial-tracked move requires quantity 0 or 1",
                error_code="serial_quantity_invalid",
            )
        if lot_id is None or line_dst.usage not in STOCK_QUANT_USAGES:
            return
        on_hand = await StockQuant.sum_quantity_for_lot(company_id, lot_id)
        if on_hand + qty > Decimal("1"):
            raise PlatformConflictError(
                "Serial number is already on hand",
                error_code="serial_quantity_invalid",
            )

    @classmethod
    async def last_done_at_by_product_id(
        cls, company_id: str, product_ids: list[str]
    ) -> dict[str, datetime]:
        """MAX(done_at) закрытых движений, ключ product_id. Пустой список — {}. Товар без закрытого движения не входит. Строка без строкового product_id или без done_at не входит."""
        if not product_ids:
            return {}
        params: list[str] = [company_id, *product_ids]
        placeholders = ", ".join(
            f"${index}" for index in range(2, len(product_ids) + 2)
        )
        rows = await execute_raw(
            "SELECT product_id, MAX(done_at) AS last_done_at FROM stock_moves WHERE company_id = $1 AND state = 'done' AND product_id IN ("
            + placeholders
            + ") GROUP BY product_id",
            params,
            using=STOCK_DB,
        )
        result: dict[str, datetime] = {}
        for row in rows:
            parsed = require_json_object(row, "stock_last_move_at")
            product_id = parsed.get("product_id")
            last_done_at = parsed.get("last_done_at")
            if isinstance(product_id, str) and isinstance(last_done_at, str):
                result[product_id] = datetime.fromisoformat(last_done_at)
            elif isinstance(product_id, str) and isinstance(last_done_at, datetime):
                result[product_id] = last_done_at
        return result

    # --- Команды леджера: граница транзакции = полоса ---

    @classmethod
    async def release_in_lane(
        cls,
        *,
        company_id: str,
        move_id: str,
        warehouse_id: str | None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Команда «снять резерв» — документ возвращается в ``confirmed``.

        Бизнес-сценарий: заказ был разложен по ячейкам, но менеджер
        передумал/переиграл приоритеты — снимаем обещание
        (``reserved_quantity`` обратно в доступное), строки резерва
        отменяются, move снова «просто принят». Использовать повторно —
        ``assign``.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            move = await cls.require_locked(company_id, move_id)
            require_stock(
                move.state in _RESERVABLE_STATES,
                "Move has no reservation to release",
                error_code="move_state_conflict",
            )
            _ = await cls.release_step(company_id=company_id, move=move)
            _ = await cls.write_state(
                company_id, move, StockMoveState.CONFIRMED
            )
            return LaneOutcome(result=move, events=[])

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def activate_in_lane(
        cls,
        *,
        company_id: str,
        move_id: str,
        warehouse_id: str | None,
        removal_strategy: StockRemovalStrategy = StockRemovalStrategy.FIFO,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Разбудить плечо маршрутной цепочки — ``waiting → резерв``.

        Бизнес-сценарий «приёмка → QC → хранение»: когда предыдущее
        плечо проведено (паллета ушла в зону контроля), следующее
        движение «снимается с паузы»: ``waiting → confirmed``, затем
        сразу раскладывается резерв по ячейкам (``reserve_step``) —
        кладовщик следующей зоны видит задание, не дожидаясь
        менеджера. Плечи разных складов исполняются каждое в своей
        полосе — ``warehouse_id`` движения задаёт ключ сериализации.

        Идемпотентно: повторный вызов над уже активным плечом —
        no-op (доклад advance может дойти дважды).
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            move = await cls.require_locked(company_id, move_id)
            if move.state in {
                StockMoveState.CONFIRMED,
                StockMoveState.PARTIALLY_AVAILABLE,
                StockMoveState.ASSIGNED,
            }:
                # Уже активно: доклад повторился или плечо будили вручную.
                return LaneOutcome(result=move, events=[])
            if move.state == StockMoveState.DONE:
                raise PlatformConflictError(
                    "Chained move is already done",
                    error_code="move_state_conflict",
                )
            if move.state == StockMoveState.CANCEL:
                raise PlatformConflictError(
                    "Chained move was cancelled",
                    error_code="move_state_conflict",
                )
            # DRAFT и WAITING → confirmed → сразу резерв.
            _ = await cls.objects.filter(
                company_id=company_id, move_id=move.move_id
            ).update(using=STOCK_DB, state=StockMoveState.CONFIRMED)
            move.state = StockMoveState.CONFIRMED
            _ = await cls.reserve_step(
                company_id=company_id,
                move=move,
                dest_location_id=None,
                owner_entity_id=None,
                removal_strategy=removal_strategy,
            )
            return LaneOutcome(result=move, events=[])

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def update_line_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str | None,
        move_line_id: str,
        done_quantity: Decimal | None,
        picked: bool | None,
        lot_id: str | None,
        location_dest_id: str | None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[StockMoveLine]:
        """Команда оператора с терминала — «я отсканировал/поправил строку».

        Рабочий интерфейс ТСД на линии: оператор внёс фактическое
        количество (``done_quantity`` — сколько реально положил/взял,
        может отличаться от резерва), отметил ``picked`` («собрано»),
        уточнил партию или переназначил ячейку приёмника.

        Пишет только в строку исполнения — остатки quant не двигаются до
        ``validate``/post. На закрытом move (done/cancel) —
        ``move_closed``: исправление проведённого — только новый
        документ.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[StockMoveLine]:
            line = await StockMoveLine.objects.filter(
                company_id=company_id, move_line_id=move_line_id
            ).for_update().get_or_none()
            if line is None:
                raise PlatformNotFoundError(
                    "Move line not found", error_code="move_line_not_found"
                )
            move = await cls.by_id_locked(company_id, line.move_id)
            if move is None or move.state in {
                StockMoveState.DONE,
                StockMoveState.CANCEL,
            }:
                raise PlatformConflictError(
                    "Move is already closed", error_code="move_closed"
                )
            if done_quantity is not None:
                require_stock(
                    done_quantity >= STOCK_ZERO,
                    "done_quantity must be >= 0",
                    error_code="done_quantity_invalid",
                )
                line.done_quantity = done_quantity
            if picked is not None:
                line.picked = picked
            if lot_id is not None:
                # Партия проверяется сразу, а не внутри post: оператору
                # нужна ошибка на вводе, а не отказ всей проводки позже.
                product = await StockProduct.by_id(company_id, move.product_id)
                if product is not None and product.tracking == StockTracking.NONE:
                    raise PlatformConflictError(
                        "Lot is not allowed for untracked product",
                        error_code="lot_not_allowed",
                    )
                lot = await StockLot.by_id_locked(company_id, lot_id)
                if lot is None:
                    raise PlatformNotFoundError(
                        "Lot not found", error_code="lot_not_found"
                    )
                if product is not None and lot.product_id != product.product_id:
                    raise PlatformConflictError(
                        "Lot belongs to another product",
                        error_code="lot_product_mismatch",
                    )
                line.lot_id = lot_id
            if location_dest_id is not None:
                # Ячейка-приёмник обязана существовать и держать класс
                # направления move: переназначить строку на partner при
                # внутреннем документе = уничтожить товар без списания.
                loc = await StockLocation.by_id(company_id, location_dest_id)
                if loc is None:
                    raise PlatformNotFoundError(
                        "Location not found", error_code="location_not_found"
                    )
                move_dst = await StockLocation.by_id(
                    company_id, move.location_dest_id
                )
                if loc.usage == StockLocationUsage.VIEW or (
                    move_dst is not None
                    and (loc.usage in STOCK_EXTERNAL_USAGES)
                    != (move_dst.usage in STOCK_EXTERNAL_USAGES)
                ):
                    raise PlatformConflictError(
                        "Line destination crosses the move's internal/external boundary",
                        error_code="location_usage_invalid",
                    )
                line.location_dest_id = location_dest_id
            _ = await line.save()
            return LaneOutcome(result=line, events=[])

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=StockMoveLine,
            body=body,
        )

    @classmethod
    async def apply_inventory_in_lane(
        cls,
        *,
        company_id: str,
        quant_id: str,
        warehouse_id: str | None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
        causation_id: str | None = None,
    ) -> LaneRun[StockMove]:
        """Приказ «утвердить инвентаризацию» — дельта становится движением.

        Сравнивает фактический подсчёт (``quant.inventory_quantity``) с
        книжным ``quantity`` и проводит StockMove на разницу через
        виртуальную локацию ``adjustment``:

        * недостача (delta < 0): ``bin → adjustment`` — списание
          (OUTBOUND-деньги/INVENTORY_LOSS: минус со склада и из оценки);
        * излишек (delta > 0): ``adjustment → bin`` — оприходование
          (INVENTORY_GAIN).

        Черновик ``inventory_quantity`` обнуляется до постинга —
        повторный apply без нового подсчёта даст ``inventory_empty``.
        Move создаётся и сразу проводится в той же транзакции: приказ
        об инвентаризации — это и есть документ движения.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[StockMove]:
            quant = await StockQuant.by_id_locked(company_id, quant_id)
            if quant is None:
                raise PlatformNotFoundError(
                    "Quant not found", error_code="quant_not_found"
                )
            if quant.inventory_quantity is None:
                raise PlatformConflictError(
                    "Quant has no pending inventory", error_code="inventory_empty"
                )
            delta = quant.inventory_quantity - quant.quantity
            if delta == STOCK_ZERO:
                raise PlatformConflictError(
                    "Inventory delta is zero", error_code="inventory_delta_zero"
                )
            inventory = await StockLocation.virtual_by_usage(
                company_id, StockLocationUsage.ADJUSTMENT
            )
            if inventory is None:
                raise PlatformNotFoundError(
                    "Virtual inventory location missing; run stock/company/init",
                    error_code="location_not_found",
                )
            product = await CatalogProduct.by_id(company_id, quant.product_id)
            if product is None:
                raise PlatformNotFoundError(
                    "Product not found", error_code="product_not_found"
                )
            now = utcnow()
            src, dst = (
                (quant.location_id, inventory.location_id)
                if delta < STOCK_ZERO
                else (inventory.location_id, quant.location_id)
            )
            move = await cls.create(
                cls(
                    move_id=new_id("mov"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    transfer_id=None,
                    product_id=quant.product_id,
                    product_qty=abs(delta),
                    product_uom_qty=abs(delta),
                    uom_id=product.uom_id,
                    location_id=src,
                    location_dest_id=dst,
                    state=StockMoveState.CONFIRMED,
                    origin_document_type="stock_inventory",
                    origin_document_id=quant.quant_id,
                    date=now,
                    created_at=now,
                )
            )
            line = StockMoveLine(
                move_line_id=new_id("mli"),
                company_id=company_id,
                move_id=move.move_id,
                warehouse_id=warehouse_id,
                product_id=quant.product_id,
                lot_id=quant.lot_id,
                owner_entity_id=quant.owner_entity_id,
                quantity=STOCK_ZERO,
                done_quantity=abs(delta),
                location_id=src,
                location_dest_id=dst,
                created_at=now,
            )
            _ = await StockMoveLine.objects.create(instance=line)
            await StockQuant.update_inventory_quantity_counted_at_and_user(quant.quant_id, None)
            posted = await cls.post_step(
                company_id=company_id,
                move=move,
                warehouse_id=warehouse_id,
                owner_entity_id=quant.owner_entity_id,
                actor_user_id=actor_user_id,
            )
            events = [
                move_done_event(
                    posted,
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    operation_code=None,
                    actor_user_id=actor_user_id,
                    causation_id=causation_id,
                ),
                *quant_changed_events(
                    posted.quants,
                    company_id=company_id,
                    move_id=posted.move.move_id,
                    actor_user_id=actor_user_id,
                    causation_id=causation_id,
                ),
            ]
            return LaneOutcome(result=posted.move, events=events)

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=StockMove,
            body=body,
        )


def _stock_move_from_row(row: JsonValue) -> StockMove:
    """Строка ``row_to_json(stock_moves)`` → StockMove."""
    parsed = require_json_object(row, "stock_move")
    raw_item = parsed["item"]
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "stock_move")
    else:
        payload = require_json_object(raw_item, "stock_move")
    return StockMove.model_validate(payload)

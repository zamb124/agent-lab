"""Волна сборки (``stock_waves``) — пачка заданий, выданная в работу разом.

Волна — это «сменное задание бригады»: диспетчер группирует открытые
строки исполнения (move_lines) — например, все заказы утренней
отправки или весь товар одного маршрута — и выпускает их в зал
одним актом. Операторы видят строки волны в очереди и разбирают их
по приоритету и последовательности обхода.

Жизненный цикл:
  * ``draft`` — набрана, строки ещё не видны как отдельная волна
    (строки уже в очереди, волна лишь помечает их ``wave_id``);
  * ``released`` — выпущена в работу: push ``stock/wave/released``,
    операторы получают задания;
  * ``done`` — все строки исполнены или отменены (вычисляется по
    дочерним строкам при каждом изменении);
  * ``cancelled`` — волна снята: строки просто теряют ``wave_id`` и
    остаются в общей очереди (сам товар и резервы не трогаем).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import STOCK_DB, new_id, stock_command_lane
from apps.stock.models.enums import StockMoveLineState, StockWaveState
from apps.stock.models.events import (
    STOCK_WAVE_RELEASED,
    StockWaveReleasedPayload,
    company_event,
)
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockWave(PlatformModel):
    """Пачка заданий склада, выпускаемая в работу одним актом.

    Поля:
      * ``name`` — человекочитаемый номер («WAVE-2026-001»);
      * ``priority`` — базовый приоритет строк волны (поднимает их
        в очереди операторов);
      * ``user_id`` — закреплённый исполнитель (волна «на одного
        кладовщика»), иначе разбирают все;
      * ``line_count`` — денормализованный счётчик строк для пульса.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_waves"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "state"]),
        ]

    wave_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    name: str = DbField(max_length=128)
    state: StockWaveState = DbField(default=StockWaveState.DRAFT, max_length=16)
    priority: int = DbField(default=0)
    user_id: str | None = DbField(default=None, max_length=64)
    line_count: int = DbField(default=0)
    stops: list[str] = DbField(default_factory=list, db_type="JSONB")
    """Путевой лист рейса: ``transfer_id`` остановок в порядке объезда.

    Строка задания получает ``stop_order`` = индекс своей накладной
    здесь — оператор волны-рейса едет остановки по очереди, а внутри
    остановки разбирает строки по ``sequence`` (обход ячеек).
    """
    released_at: datetime | None = DbField(default=None)
    done_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    # --- чтение -------------------------------------------------------------

    @classmethod
    async def by_id(cls, company_id: str, wave_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, wave_id=wave_id
        ).get_or_none()

    @classmethod
    async def list_for_warehouse(
        cls,
        company_id: str,
        warehouse_id: str,
        *,
        state: StockWaveState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Self]:
        q = cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        )
        if state is not None:
            q = q.filter(state=state)
        return await q.order_by("-created_at").limit(limit).offset(offset).all()

    # --- запись (внутри полосы склада) -------------------------------------

    @classmethod
    async def create_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        name: str | None,
        move_line_ids: list[str],
        move_ids: list[str],
        priority: int,
        user_id: str | None,
        stop_transfer_ids: list[str] | None = None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[StockWave]:
        """Собрать волну из открытых строк — «сформировать сменное задание».

        В полосе склада: указанные строки (по move_line_ids и/или всем
        открытым строкам move_ids) проверяются, помечаются ``wave_id``
        и общим приоритетом волны — дальше они обычные строки очереди.
        Строка, уже в другой волне, отклоняет создание: задание не
        должно ехать в двух сменных нарядах сразу.
        """
        from apps.stock.models.move_line import StockMoveLine

        async def body(_scope: LaneScope) -> LaneOutcome[StockWave]:
            line_ids = list(move_line_ids)
            if move_ids:
                extra = await StockMoveLine.list_open_for_moves(
                    company_id, move_ids
                )
                line_ids += [x.move_line_id for x in extra]
            line_ids = sorted(set(line_ids))
            if not line_ids:
                raise PlatformConflictError(
                    "Wave has no lines to group",
                    error_code="wave_empty",
                )
            lines = await StockMoveLine.by_ids_locked(company_id, line_ids)
            found = {x.move_line_id for x in lines}
            if len(found) != len(line_ids):
                raise PlatformNotFoundError(
                    "Move line not found", error_code="move_line_not_found"
                )
            for line in lines:
                if line.state != StockMoveLineState.OPEN:
                    raise PlatformConflictError(
                        "Move line is not open",
                        error_code="move_line_not_open",
                    )
                if line.wave_id is not None:
                    raise PlatformConflictError(
                        "Move line is already in another wave",
                        error_code="wave_line_conflict",
                    )
            # Путевой лист: явный порядок остановок + оставшиеся
            # накладные — в порядке встречи их строк. Накладные
            # остановок проверены сервисом до входа в полосу (та же
            # компания и склад); здесь страхуемся только от повторов.
            stops = list(stop_transfer_ids or [])
            if len(set(stops)) != len(stops):
                raise PlatformConflictError(
                    "Wave stop is duplicated",
                    error_code="wave_stop_duplicate",
                )
            for line in lines:
                if line.transfer_id is not None and line.transfer_id not in stops:
                    stops.append(line.transfer_id)
            stop_of = {tid: index for index, tid in enumerate(stops)}
            wave = cls(
                wave_id=new_id("wav"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                name=name or f"WAVE-{utcnow():%Y%m%d-%H%M%S}",
                state=StockWaveState.DRAFT,
                priority=priority,
                user_id=user_id,
                line_count=len(lines),
                stops=stops,
                created_at=utcnow(),
            )
            wave = await cls.objects.create(instance=wave)
            by_stop: dict[int, list[str]] = {}
            for line in lines:
                index = (
                    stop_of[line.transfer_id]
                    if line.transfer_id is not None
                    else len(stops)
                )
                by_stop.setdefault(index, []).append(line.move_line_id)
            for index, ids in by_stop.items():
                _ = await StockMoveLine.objects.filter(
                    company_id=company_id, move_line_id__in=ids
                ).update(
                    using=STOCK_DB,
                    wave_id=wave.wave_id,
                    priority=priority,
                    stop_order=index,
                    assigned_user_id=user_id
                    if user_id is not None
                    else None,
                )
            return LaneOutcome(result=wave, events=[])

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            command_type=command_type,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def release_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        wave_id: str,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[StockWave]:
        """Выпуск волны в работу — push операторам после commit.

        «Выпустить» = перевести ``draft → released``: строки уже в
        очереди, но событие ``stock/wave/released`` — сигнал бригаде
        «волна пошла», а диспетчеру — точка фиксации плана.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[StockWave]:
            wave = await cls.objects.filter(
                company_id=company_id, wave_id=wave_id
            ).for_update().get_or_none()
            if wave is None:
                raise PlatformNotFoundError(
                    "Wave not found", error_code="wave_not_found"
                )
            if wave.state != StockWaveState.DRAFT:
                raise PlatformConflictError(
                    "Wave is not in draft state",
                    error_code="wave_state_conflict",
                )
            now = utcnow()
            _ = await cls.objects.filter(
                company_id=company_id, wave_id=wave_id
            ).update(
                using=STOCK_DB,
                state=StockWaveState.RELEASED,
                released_at=now,
            )
            wave.state = StockWaveState.RELEASED
            wave.released_at = now
            event = company_event(
                STOCK_WAVE_RELEASED,
                StockWaveReleasedPayload(
                    company_id=company_id,
                    wave_id=wave.wave_id,
                    warehouse_id=wave.warehouse_id,
                    name=wave.name,
                    line_count=wave.line_count,
                    released_at=now.isoformat(),
                ),
                company_id=company_id,
                actor_user_id=actor_user_id,
            )
            return LaneOutcome(result=wave, events=[event])

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            command_type=command_type,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def refresh_state(cls, company_id: str, wave_id: str) -> None:
        """Пересчёт состояния по дочерним строкам — вызывается после done.

        Все строки закрыты (done/cancelled) → волна ``done``. Дешёвая
        денормализация для пульса, без собственной транзакции: читает
        то, что уже закоммичено.
        """
        from apps.stock.models.move_line import StockMoveLine

        open_count = await StockMoveLine.objects.filter(
            company_id=company_id,
            wave_id=wave_id,
            state=StockMoveLineState.OPEN,
        ).count()
        if open_count > 0:
            return
        _ = await cls.objects.filter(
            company_id=company_id,
            wave_id=wave_id,
            state=StockWaveState.RELEASED,
        ).update(using=STOCK_DB, state=StockWaveState.DONE, done_at=utcnow())


__all__ = ["StockWave"]

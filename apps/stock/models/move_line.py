"""Строки исполнения накладной (stock_move_lines) — складские задания.

Если StockMove — «строка накладной» (что и сколько), то StockMoveLine —
«конкретное поручение кладовщику»: из какой ячейки взять, какой партии,
сколько реально отсканировал, кто и когда исполнил.

Один move может разложиться на несколько строк: «взять 6 шт из ячейки
A-01» + «добрать 2 шт из A-07» = две строки исполнения одной позиции
накладной.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import (
    QTY_DB,
    STOCK_DB,
    STOCK_ZERO,
    new_id,
    stock_command_lane,
)
from apps.stock.models.enums import StockMoveLineKind, StockMoveLineState
from apps.stock.models.events import (
    STOCK_MOVE_LINE_ASSIGNED,
    STOCK_MOVE_LINE_EXCEPTION,
    StockMoveLineAssignedPayload,
    StockMoveLineExceptionPayload,
    company_event,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.resource import StockResource
from apps.stock.models.resource_type import StockResourceType
from apps.stock.models.storage_rules import resource_allows
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.events.contract import PlatformEvent
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockMoveLineClaimResult(StrictBaseModel):
    """Исход захвата/освобождения заданий — обработанные строки."""

    move_line_ids: list[str]
    assigned_user_id: str | None = None
    resource_id: str | None = None


class StockMoveLineExceptionResult(StrictBaseModel):
    """Исход исключения по заданию — сокращение + задание пересчёта."""

    move_line_id: str
    count_line_id: str
    shortage: Decimal


class StockMoveLine(PlatformModel):
    """Поручение кладовщику внутри строки накладной. Таблица ``stock_move_lines``.

    Виды заданий (``kind``):
      * ``quantity`` — взять/положить N единиц товара: обычная строка
        резерва и исполнения;
      * ``container`` — переместить контейнер целиком (``container_id``,
        без количества): «перевези паллету PLT-012 в зону B»;
      * ``count`` — задание пересчёта ячейки (циклическая
        инвентаризация, Фаза 6).

    Поля исполнения:
      * ``quantity`` — сколько зарезервировано под строку;
      * ``done_quantity`` — сколько реально отсканировал оператор;
        именно она становится фактом при проведении;
      * ``lot_id``, ``location_id``/``location_dest_id`` — партия и
        конкретные ячейки этой операции;
      * ``state`` — ``open``/``done``/``cancelled``;
      * ``assigned_user_id``, ``resource_id``, ``claimed_at`` — кому
        поручено и на какой технике (Фаза 4 — очередь заданий);
      * ``wave_id``, ``stop_order``, ``sequence``, ``priority`` —
        волна сборки, позиция остановки в её рейсе и порядок обхода
        ячеек;
      * ``done_at``/``done_by_user_id`` — когда и кем исполнено.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_move_lines"
        indexes: list[Index] = [
            Index(["company_id", "move_id"]),
            Index(["company_id", "lot_id"]),
            Index(["company_id", "warehouse_id", "state"]),
            Index(["company_id", "assigned_user_id", "state"]),
            Index(["company_id", "wave_id", "state"]),
            Index(["company_id", "container_id"]),
        ]

    move_line_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    move_id: str = DbField(max_length=64)
    transfer_id: str | None = DbField(default=None, max_length=64)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    kind: StockMoveLineKind = DbField(default=StockMoveLineKind.QUANTITY)
    state: StockMoveLineState = DbField(default=StockMoveLineState.OPEN)
    product_id: str = DbField(max_length=64)
    lot_id: str | None = DbField(default=None, max_length=64)
    container_id: str | None = DbField(default=None, max_length=64)
    """`location_id` контейнера для `kind=container` — история перемещений."""
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    quantity: Decimal = DbField(default=STOCK_ZERO, db_type=QTY_DB)
    done_quantity: Decimal = DbField(default=STOCK_ZERO, db_type=QTY_DB)
    picked: bool = DbField(default=False)
    location_id: str = DbField(max_length=64)
    location_dest_id: str = DbField(max_length=64)
    assigned_user_id: str | None = DbField(default=None, max_length=64)
    resource_id: str | None = DbField(default=None, max_length=64)
    claimed_at: datetime | None = DbField(default=None)
    wave_id: str | None = DbField(default=None, max_length=64)
    sequence: int = DbField(default=0)
    """Порядок обхода — ``pick_sequence`` рабочей ячейки строки."""
    stop_order: int = DbField(default=0)
    """Остановка рейса волны — индекс ``transfer_id`` в ``wave.stops``."""
    priority: int = DbField(default=0)
    done_at: datetime | None = DbField(default=None)
    done_by_user_id: str | None = DbField(default=None, max_length=64)
    created_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def list_open_for_move_by_created_at_asc(cls, company_id: str, move_id: str) -> list[Self]:
        """Открытые строки движения, ORDER BY created_at ASC. Предела нет. Пустые поля не проверяются."""
        return await cls.objects.filter(
            company_id=company_id,
            move_id=move_id,
            state=StockMoveLineState.OPEN,
        ).order_by("created_at").all()

    @classmethod
    async def list_open_for_move_by_sequence_created_at_asc(cls, company_id: str, move_id: str) -> list[Self]:
        """Открытые строки движения, ORDER BY sequence, created_at, move_line_id ASC. Предела нет. Пустые поля не проверяются."""
        return await cls.objects.filter(
            company_id=company_id,
            move_id=move_id,
            state=StockMoveLineState.OPEN,
        ).order_by("sequence", "created_at", "move_line_id").all()

    @classmethod
    async def list_for_move_by_created_at_asc(cls, company_id: str, move_id: str) -> list[Self]:
        """Все строки движения, ORDER BY created_at ASC. Предела нет. Пустые поля не проверяются."""
        return await cls.objects.filter(
            company_id=company_id, move_id=move_id
        ).order_by("created_at").all()

    @classmethod
    async def list_for_moves_by_created_at_asc(
        cls, company_id: str, move_ids: list[str]
    ) -> list[Self]:
        """Все строки этих движений, ORDER BY created_at ASC. Пустой move_ids — []. Предела нет."""
        if not move_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id, move_id__in=move_ids
        ).order_by("created_at").all()

    @classmethod
    async def by_id(cls, company_id: str, move_line_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, move_line_id=move_line_id
        ).get_or_none()

    @classmethod
    async def list_done_by_user_by_done_at_asc(
        cls,
        company_id: str,
        warehouse_id: str,
        user_id: str,
        since: datetime,
    ) -> list[Self]:
        """Исполненные оператором строки склада за окно, ORDER BY done_at ASC."""
        return await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            state=StockMoveLineState.DONE,
            done_by_user_id=user_id,
            done_at__gte=since,
        ).order_by("done_at").all()

    @classmethod
    async def mark_done(
        cls,
        company_id: str,
        move_line_ids: list[str],
        *,
        done_at: datetime,
        done_by_user_id: str | None,
    ) -> None:
        """Перевод исполненных заданий в `done` (вызывается из post_step)."""
        if not move_line_ids:
            return
        _ = await cls.objects.filter(
            company_id=company_id, move_line_id__in=move_line_ids
        ).update(
            using=STOCK_DB,
            state=StockMoveLineState.DONE,
            done_at=done_at,
            done_by_user_id=done_by_user_id,
        )

    # --- очередь заданий (Фаза 4) ---

    @classmethod
    async def list_open_queue_by_priority_desc_stop_sequence_and_created_at(
        cls,
        company_id: str,
        warehouse_id: str,
        *,
        assigned_user_id: str | None = None,
        zone_location_id: str | None = None,
        wave_id: str | None = None,
        limit: int = 100,
    ) -> list[Self]:
        """Открытая очередь склада, ORDER BY priority DESC, stop_order, sequence, created_at. assigned_user_id, zone_location_id и wave_id равные None не фильтруют. Пустое поддерево зоны — []. limit по умолчанию 100 и в теле не проверяется. Сначала срочное, затем остановка рейса, затем обход ячеек."""
        q = cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            state=StockMoveLineState.OPEN,
        )
        if assigned_user_id is not None:
            q = q.filter(assigned_user_id=assigned_user_id)
        if wave_id is not None:
            q = q.filter(wave_id=wave_id)
        if zone_location_id is not None:
            zone_ids = await StockLocation.list_subtree_ids_by_parent_path_asc(
                company_id, zone_location_id
            )
            if not zone_ids:
                return []
            q = q.filter(location_id__in=zone_ids)
        return await q.order_by(
            "-priority", "stop_order", "sequence", "created_at"
        ).limit(limit).all()

    @classmethod
    async def list_open_for_moves_by_created_at_asc(
        cls, company_id: str, move_ids: list[str]
    ) -> list[Self]:
        """Открытые строки этих движений, ORDER BY created_at ASC. Пустой move_ids — []. Предела нет."""
        if not move_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id,
            move_id__in=move_ids,
            state=StockMoveLineState.OPEN,
        ).order_by("created_at").all()

    @classmethod
    async def list_open_for_moves_by_sequence_created_at_asc(
        cls, company_id: str, move_ids: list[str]
    ) -> list[Self]:
        """Открытые строки этих движений, ORDER BY sequence, created_at, move_line_id ASC — порядок обхода из очереди. Пустой move_ids — []. Пустые поля не проверяются."""
        if not move_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id,
            move_id__in=move_ids,
            state=StockMoveLineState.OPEN,
        ).order_by("sequence", "created_at", "move_line_id").all()

    @classmethod
    async def list_unordered_locked_by_ids(
        cls, company_id: str, move_line_ids: list[str]
    ) -> list[Self]:
        """Строки под SELECT FOR UPDATE внутри полосы склада. Порядка нет. Пустой список id — []."""
        if not move_line_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id, move_line_id__in=move_line_ids
        ).for_update().all()

    @classmethod
    async def list_unordered_stale_claimed(
        cls,
        company_id: str,
        warehouse_id: str,
        claimed_before: datetime,
    ) -> list[Self]:
        """Открытые строки склада с claimed_at раньше claimed_before. Порядка и limit нет. Тик stock_claims_gc отпускает их в общую очередь."""
        return await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            state=StockMoveLineState.OPEN,
            claimed_at__lt=claimed_before,
        ).all()

    @classmethod
    async def list_unordered_open_for_warehouse(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Строки склада в state OPEN. Порядка и limit нет."""
        return await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            state=StockMoveLineState.OPEN,
        ).all()

    @classmethod
    async def clear_claim_fields(
        cls, company_id: str, move_line_id: str
    ) -> None:
        """Снять захват со строки — возврат задания в общую очередь.

        Claims-GC тик и «отказаться от задания» делят эту правку:
        ``assigned_user_id``/``resource_id``/``claimed_at`` обнуляются,
        строка снова видна всем через ``next``.
        """
        _ = await cls.objects.filter(
            company_id=company_id, move_line_id=move_line_id
        ).update(
            using=STOCK_DB,
            assigned_user_id=None,
            resource_id=None,
            claimed_at=None,
        )

    @classmethod
    async def claim_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str | None,
        move_line_ids: list[str],
        user_id: str,
        resource_id: str | None,
        claimed: bool,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[StockMoveLineClaimResult]:
        """Захват заданий оператором — «эти строки теперь мои».

        Бизнес-смысл: на складе одно поручение исполняет один человек
        (или одна тележка/кран) — иначе два кладовщика поедут за одной
        паллетой. Поэтому захват атомарен: внутри полосы склада строки
        читаются под ``FOR UPDATE``, и любая чужая/исполненная строка
        отклоняет весь пакет — частичного «мне взяли половину» нет.

        ``claimed=True`` — оператор сам взял из очереди (claim);
        ``claimed=False`` — задания выдал диспетчер (assign) — семантика
        в событии, чтобы очереди на экранах отличали «взял» от «дал».
        """

        async def body(
            _scope: LaneScope,
        ) -> LaneOutcome[StockMoveLineClaimResult]:
            lines = await cls.list_unordered_locked_by_ids(company_id, move_line_ids)
            found = {line.move_line_id: line for line in lines}
            missing = [i for i in move_line_ids if i not in found]
            if missing:
                raise PlatformNotFoundError(
                    "Move line not found", error_code="move_line_not_found"
                )
            if resource_id is not None:
                # Ресурс захвата проверяется в той же полосе, что и
                # строки: существует, активен и способен исполнить
                # КАЖДУЮ строку пакета — иначе задание повисло бы на
                # технике, которая физически его не потянет.
                resource = await StockResource.by_id(company_id, resource_id)
                if resource is None:
                    raise PlatformNotFoundError(
                        "Resource not found", error_code="resource_not_found"
                    )
                if not resource.is_active:
                    raise PlatformConflictError(
                        "Resource is inactive", error_code="resource_inactive"
                    )
                resource_type = await StockResourceType.by_id(
                    company_id, resource.resource_type_id
                )
                if resource_type is None:
                    raise PlatformNotFoundError(
                        "Resource type not found",
                        error_code="resource_type_not_found",
                    )
                fit_locations = await StockLocation.found_in_company_by_ids(
                    company_id,
                    sorted(
                        {
                            loc_id
                            for line in lines
                            for loc_id in (
                                line.location_id,
                                line.location_dest_id,
                            )
                        }
                        | {
                            line.container_id
                            for line in lines
                            if line.container_id is not None
                        }
                    ),
                )
                for line in lines:
                    line_src = fit_locations.get(line.location_id)
                    line_dst = fit_locations.get(line.location_dest_id)
                    line_container = (
                        fit_locations.get(line.container_id)
                        if line.container_id is not None
                        else None
                    )
                    violation = resource_allows(
                        resource_type=resource_type,
                        container_type_id=(
                            line_container.container_type_id
                            if line_container is not None
                            else None
                        ),
                        loose=line.kind != StockMoveLineKind.CONTAINER,
                        src_level=(
                            line_src.level if line_src is not None else None
                        ),
                        dst_level=(
                            line_dst.level if line_dst is not None else None
                        ),
                        src_storage_type_id=(
                            line_src.storage_type_id
                            if line_src is not None
                            else None
                        ),
                        dst_storage_type_id=(
                            line_dst.storage_type_id
                            if line_dst is not None
                            else None
                        ),
                        load_weight=None,
                    )
                    if violation is not None:
                        raise PlatformConflictError(
                            "Line does not fit the resource",
                            error_code=violation,
                        )
            now = utcnow()
            events: list[PlatformEvent] = []
            for line in lines:
                if line.state != StockMoveLineState.OPEN:
                    raise PlatformConflictError(
                        "Move line is not open",
                        error_code="move_line_not_open",
                    )
                if (
                    line.assigned_user_id is not None
                    and line.assigned_user_id != user_id
                ):
                    raise PlatformConflictError(
                        "Move line is claimed by another operator",
                        error_code="move_line_claimed",
                    )
                _ = await cls.objects.filter(
                    company_id=company_id,
                    move_line_id=line.move_line_id,
                ).update(
                    using=STOCK_DB,
                    assigned_user_id=user_id,
                    resource_id=resource_id,
                    claimed_at=now,
                )
                events.append(
                    company_event(
                        STOCK_MOVE_LINE_ASSIGNED,
                        StockMoveLineAssignedPayload(
                            company_id=company_id,
                            move_line_id=line.move_line_id,
                            move_id=line.move_id,
                            transfer_id=line.transfer_id,
                            warehouse_id=line.warehouse_id,
                            wave_id=line.wave_id,
                            assigned_user_id=user_id,
                            resource_id=resource_id,
                            claimed=claimed,
                        ),
                        company_id=company_id,
                        actor_user_id=actor_user_id,
                    )
                )
            return LaneOutcome(
                result=StockMoveLineClaimResult(
                    move_line_ids=move_line_ids,
                    assigned_user_id=user_id,
                    resource_id=resource_id,
                ),
                events=events,
            )

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            command_type=command_type,
            result_type=StockMoveLineClaimResult,
            body=body,
        )

    @classmethod
    async def release_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str | None,
        move_line_ids: list[str],
        user_id: str | None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[StockMoveLineClaimResult]:
        """Вернуть задания в общую очередь — «отпустить».

        Оператор отпускает только свои строки (``user_id``), диспетчер
        может снимать чужие (``user_id=None`` — без проверки владельца).
        Резерв товара строки не трогаем: освобождение — это про «кто
        несёт», а не про «сколько обещано».
        """

        async def body(
            _scope: LaneScope,
        ) -> LaneOutcome[StockMoveLineClaimResult]:
            lines = await cls.list_unordered_locked_by_ids(company_id, move_line_ids)
            found = {line.move_line_id: line for line in lines}
            missing = [i for i in move_line_ids if i not in found]
            if missing:
                raise PlatformNotFoundError(
                    "Move line not found", error_code="move_line_not_found"
                )
            for line in lines:
                if (
                    user_id is not None
                    and line.assigned_user_id is not None
                    and line.assigned_user_id != user_id
                ):
                    raise PlatformConflictError(
                        "Move line is claimed by another operator",
                        error_code="move_line_claimed",
                    )
                _ = await cls.objects.filter(
                    company_id=company_id,
                    move_line_id=line.move_line_id,
                ).update(
                    using=STOCK_DB,
                    assigned_user_id=None,
                    resource_id=None,
                    claimed_at=None,
                )
            return LaneOutcome(
                result=StockMoveLineClaimResult(move_line_ids=move_line_ids),
                events=[],
            )

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            command_type=command_type,
            result_type=StockMoveLineClaimResult,
            body=body,
        )

    @classmethod
    async def report_exception_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str | None,
        move_line_id: str,
        shortage: Decimal,
        reason: str,
        file_ids: list[str],
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[StockMoveLineExceptionResult]:
        """Исключение по заданию: «пришёл за товаром — а его нет».

        Бизнес-сценарий: кладовщик подошёл к ячейке A-01 за 6 шт по
        заданию, а лежит только 4 (недостача) или товар битый (бой).
        Одна транзакция полосы склада делает три вещи:

        1. Строка укорачивается на недостачу: ``quantity -= shortage``
           — требование возвращается в «незарезервированное» и пойдёт
           в перерезерв при следующем ``assign`` (возьмём из другой
           ячейки).
        2. Резерв на исходном quant'е отпускается:
           ``reserved -= shortage`` — обещание на «пустое место»
           снимается, чтобы никто больше сюда не поехал.
        3. На ячейку ставится задание пересчёта ``kind=count``: книжный
           остаток подозрителен — его исправит инвентаризация
           (count → ``inventory_apply`` запишет дельту bin↔adjustment).

        Физическое ``quantity`` quant'а здесь не трогаем — книжные
        цифры исправляет только пересчёт, а не факт «не нашли».
        """
        from apps.stock.models.quant import StockQuant

        async def body(
            _scope: LaneScope,
        ) -> LaneOutcome[StockMoveLineExceptionResult]:
            lines = await cls.list_unordered_locked_by_ids(company_id, [move_line_id])
            if not lines:
                raise PlatformNotFoundError(
                    "Move line not found", error_code="move_line_not_found"
                )
            line = lines[0]
            if line.state != StockMoveLineState.OPEN:
                raise PlatformConflictError(
                    "Move line is not open",
                    error_code="move_line_not_open",
                )
            if shortage <= STOCK_ZERO or shortage > line.quantity:
                raise PlatformConflictError(
                    "Shortage is out of the line quantity range",
                    error_code="move_line_exception_qty",
                )
            # done урезается вместе с требованием: строка не может
            # исполниться больше, чем реально осталось забрать —
            # иначе post отгрузил бы «недостающие» единицы как факт.
            new_quantity = line.quantity - shortage
            new_done = min(line.done_quantity, new_quantity)
            _ = await cls.objects.filter(
                company_id=company_id, move_line_id=move_line_id
            ).update(
                using=STOCK_DB,
                quantity=new_quantity,
                done_quantity=new_done,
            )
            line.quantity = new_quantity
            line.done_quantity = new_done
            if line.kind == StockMoveLineKind.QUANTITY:
                # Отпуск резерва на источнике — обещание снимается
                # ровно на недостачу (reserved-защита от минуса внутри).
                quant = await StockQuant.by_key_locked(
                    company_id=company_id,
                    product_id=line.product_id,
                    location_id=line.location_id,
                    lot_id=line.lot_id,
                    owner_entity_id=line.owner_entity_id,
                )
                if quant is not None and quant.reserved_quantity > STOCK_ZERO:
                    freed = min(shortage, quant.reserved_quantity)
                    _ = await StockQuant.objects.filter(
                        company_id=company_id, quant_id=quant.quant_id
                    ).update(
                        using=STOCK_DB,
                        reserved_quantity=quant.reserved_quantity - freed,
                    )
            now = utcnow()
            count_line = cls(
                move_line_id=new_id("mli"),
                company_id=company_id,
                move_id=line.move_id,
                transfer_id=line.transfer_id,
                warehouse_id=line.warehouse_id,
                kind=StockMoveLineKind.COUNT,
                product_id=line.product_id,
                lot_id=line.lot_id,
                owner_entity_id=line.owner_entity_id,
                quantity=STOCK_ZERO,
                done_quantity=STOCK_ZERO,
                location_id=line.location_id,
                location_dest_id=line.location_id,
                priority=line.priority + 1,
                created_at=now,
            )
            count_line = await cls.objects.create(instance=count_line)
            event = company_event(
                STOCK_MOVE_LINE_EXCEPTION,
                StockMoveLineExceptionPayload(
                    company_id=company_id,
                    move_line_id=line.move_line_id,
                    move_id=line.move_id,
                    transfer_id=line.transfer_id,
                    warehouse_id=line.warehouse_id,
                    product_id=line.product_id,
                    location_id=line.location_id,
                    shortage=shortage,
                    reason=reason,
                    file_ids=file_ids,
                    count_line_id=count_line.move_line_id,
                    reported_by=actor_user_id,
                ),
                company_id=company_id,
                actor_user_id=actor_user_id,
            )
            return LaneOutcome(
                result=StockMoveLineExceptionResult(
                    move_line_id=line.move_line_id,
                    count_line_id=count_line.move_line_id,
                    shortage=shortage,
                ),
                events=[event],
            )

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            command_type=command_type,
            result_type=StockMoveLineExceptionResult,
            body=body,
        )

"""Реестр складских документов (stock_transfers).

StockTransfer — «шапка накладной»: документ, который группирует строки-
движения (StockMove) одной хозяйственной операции. Приёмка поставки,
отгрузка заказа, перемещение между складами — всё это transfer с
номером вида ``WH/IN/00042``, штрихкодом и контрагентом.

Для бухгалтера: если StockMove — «проводка одной позиции», то
StockTransfer — весь приходный/расходный ордер целиком. Его ``state``
— проекция состояний его move: документ «исполнен», когда все его
строки проведены.

Типы связей документов:

* ``backorder_of_id`` — документ-должник: когда основная накладная
  исполнена частично (не хватило товара), недовыполненный остаток
  оформляется отдельным transfer-наследником, который ждёт следующей
  поставки. Цепочка backorder'ов видна по этой ссылке.
* ``return_of_id`` — возврат: обратный документ к исходной отгрузке
  (клиент вернул товар → новый transfer «клиент → склад»).
* ``origin_document_*`` — внешнее основание (заказ, счёт) в другой
  системе.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.barcode_index import StockBarcodeIndex
from apps.stock.models.common import (
    STOCK_DB,
    STOCK_ZERO,
    StockMoveSpec,
    new_id,
    stock_warehouse_lane,
)
from apps.stock.models.decision import StockDecision
from apps.stock.models.enums import (
    STOCK_EXTERNAL_USAGES,
    BackorderPolicy,
    StockBarcodeEntityType,
    StockMoveLineKind,
    StockMoveLineState,
    StockMoveState,
    StockRemovalStrategy,
    StockTracking,
    StockTransferState,
)
from apps.stock.models.events import (
    STOCK_TRANSFER_DONE,
    StockTransferDonePayload,
    company_event,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.move import (
    PostedMove,
    StockMove,
    move_done_event,
    quant_changed_events,
)
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.operation_type import StockOperationType
from apps.stock.models.product import StockProduct
from apps.stock.models.route import StockRoute
from apps.stock.models.unit_of_measure import UnitOfMeasure
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.events.contract import PlatformEvent
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockTransfer(PlatformModel):
    """Шапка складской накладной. Таблица ``stock_transfers``.

    * ``name`` — человекочитаемый номер ``WH/IN/00001``: префикс от
      операции (``name_prefix`` на типе операции) + сквозной номер без
      пропусков — как нумерация ордеров в учёте.
    * ``operation_type_id`` — вид операции (приёмка/отгрузка/внутренняя);
      от него документ наследует политики резерва и backorder.
    * ``partner_entity_id`` — контрагент (поставщик/клиент);
      ``owner_entity_id`` — владелец консигнации, если принимаем чужой
      товар на хранение.
    * штрихкод накладной для сканирования на гейте регистрируется в
      ``stock_barcodes`` (``entity_type=transfer``) при создании —
      атомарно с самим документом.
    * ``state`` — проекция состояний его StockMove (пишет только
      движок): ``draft`` → по строкам ``confirmed/assigned`` → ``done``.
    * ``priority`` / ``date_deadline`` — срочность для волн и заданий.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_transfers"
        indexes: list[Index] = [
            Index(["company_id", "name"], unique=True),
            Index(["company_id", "warehouse_id", "state"]),
            Index(["company_id", "operation_type_id", "state"]),
        ]

    transfer_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    operation_type_id: str = DbField(max_length=64)
    partner_entity_id: str | None = DbField(default=None, max_length=64)
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    name: str = DbField(max_length=64)
    state: StockTransferState = DbField(default=StockTransferState.DRAFT)
    scheduled_at: datetime | None = DbField(default=None)
    origin_document_type: str | None = DbField(default=None, max_length=64)
    origin_document_id: str | None = DbField(default=None, max_length=64)
    backorder_of_id: str | None = DbField(default=None, max_length=64)
    return_of_id: str | None = DbField(default=None, max_length=64)
    priority: int = DbField(default=0)
    """Приоритет документа — наследуется строками заданий и волнами."""
    date_deadline: datetime | None = DbField(default=None)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, transfer_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).get_or_none()

    @classmethod
    async def found_in_company_by_ids(
        cls, company_id: str, transfer_ids: list[str]
    ) -> dict[str, Self]:
        if not transfer_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, transfer_id__in=transfer_ids
        ).all()
        return {row.transfer_id: row for row in rows}

    @classmethod
    async def by_id_locked(cls, company_id: str, transfer_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).for_update().get_or_none()

    @classmethod
    async def list_by_created_at_desc(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None,
        state: StockTransferState | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Окно накладных компании, ORDER BY created_at DESC, limit и offset. warehouse_id и state равные None не фильтруют."""
        query = cls.objects.filter(company_id=company_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        if state is not None:
            query = query.filter(state=state)
        return await query.order_by("-created_at").limit(limit).offset(offset).all()

    @classmethod
    async def count_by_warehouse_and_state(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None,
        state: StockTransferState | None,
    ) -> int:
        """Счёт накладных компании. warehouse_id и state равные None не фильтруют."""
        query = cls.objects.filter(company_id=company_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        if state is not None:
            query = query.filter(state=state)
        return await query.count()

    @classmethod
    async def _seq_name(cls, scope: LaneScope, prefix: str) -> str:
        """``WH/IN/00001`` — no-gap номер из ``LaneCursor`` той же транзакции."""
        value = await scope.next_value(f"stock_transfer_name:{prefix}")
        return f"{prefix}/{value:05d}"

    @classmethod
    async def refresh_state(cls, company_id: str, transfer_id: str) -> StockTransferState:
        """Свернуть статусы строк в статус документа.

        Как читает кладовщик накладную:
          * все строки done/отменены → документ ``done``;
          * часть строк ещё резервируется → ``partially_available``;
          * все только подтверждены → ``confirmed``; и т.д.
        Вызывается только движком внутри tx — сам документ себя не
        пересчитывает.
        """
        moves = await StockMove.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).all()
        states = {m.state for m in moves}
        if not moves or states == {StockMoveState.CANCEL}:
            projected = StockTransferState.CANCEL
        elif states == {StockMoveState.DONE} or states <= {
            StockMoveState.DONE,
            StockMoveState.CANCEL,
        }:
            projected = StockTransferState.DONE
        elif states == {StockMoveState.DRAFT}:
            projected = StockTransferState.DRAFT
        elif states <= {StockMoveState.CONFIRMED, StockMoveState.WAITING}:
            projected = StockTransferState.CONFIRMED
        elif StockMoveState.ASSIGNED in states and states <= {
            StockMoveState.ASSIGNED,
            StockMoveState.DONE,
            StockMoveState.CANCEL,
        }:
            projected = StockTransferState.ASSIGNED
        else:
            projected = StockTransferState.PARTIALLY_AVAILABLE
        _ = await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).update(using=STOCK_DB, state=projected, updated_at=utcnow())
        return projected

    @classmethod
    async def done_event_after_move(
        cls,
        *,
        company_id: str,
        move: StockMove,
        operation_code: str | None,
        actor_user_id: str,
        causation_id: str | None,
        done_at: datetime,
    ) -> PlatformEvent | None:
        """Пересчёт накладной после закрытия её move скан-коммитом.

        Накладная — проекция своих строк: когда последняя строка
        проведена по ТСД, документ должен перейти в ``done`` в той же
        lane-транзакции — иначе UI/репорты увидят «проведено по факту,
        но документ в работе». Событие ``stock/transfer/done``
        отдаём один раз — строго при переходе состояния, повторный
        вызов на уже закрытом документе молчит.

        Хук вызывается из ``StockMove.post_lines_in_lane``: модель
        move не импортирует StockTransfer (иначе — цикл
        move↔transfer), колбек подаёт вызывающий сервис.
        """
        if move.transfer_id is None:
            return None
        transfer = await cls.by_id_locked(company_id, move.transfer_id)
        if transfer is None:
            return None
        prev_state = transfer.state
        final_state = await cls.refresh_state(company_id, move.transfer_id)
        if (
            final_state != StockTransferState.DONE
            or prev_state == StockTransferState.DONE
        ):
            return None
        return company_event(
            STOCK_TRANSFER_DONE,
            StockTransferDonePayload(
                company_id=company_id,
                transfer_id=transfer.transfer_id,
                warehouse_id=transfer.warehouse_id,
                operation_type_id=transfer.operation_type_id,
                operation_code=operation_code,
                name=transfer.name,
                partner_entity_id=transfer.partner_entity_id,
                backorder_of_id=transfer.backorder_of_id,
                return_of_id=transfer.return_of_id,
                backorder_transfer_id=None,
                move_ids=[move.move_id],
                origin_document_type=transfer.origin_document_type,
                origin_document_id=transfer.origin_document_id,
                done_at=done_at.isoformat(),
            ),
            company_id=company_id,
            actor_user_id=actor_user_id,
            causation_id=causation_id,
        )

    @classmethod
    async def _create_backorder(
        cls,
        *,
        company_id: str,
        scope: LaneScope,
        source: Self,
        residual_posts: list[PostedMove],
    ) -> Self | None:
        """Документ-должник на недопоставленный остаток.

        Сценарий: заказали 10 шт, смогли отгрузить 6 — остаток 4 шт
        уходит в новый transfer ``WH/OUT/00043`` с ``backorder_of_id``
        на исходную накладную. Каждый недовыполненный move копируется
        со спросом ``product_qty = остаток`` в state ``confirmed`` —
        ждёт следующей поставки и повторной раскладки резерва.

        Только внутри lane-транзакции ``validate_in_lane``: backorder —
        часть того же коммита, что и done основного документа.
        """
        residual_ids = [
            posted.move.move_id
            for posted in residual_posts
            if posted.move.product_qty - posted.done_qty > STOCK_ZERO
        ]
        if not residual_ids:
            return None
        now = utcnow()
        prefix = source.name.rsplit("/", 1)[0]
        backorder = cls(
            transfer_id=new_id("trf"),
            company_id=company_id,
            warehouse_id=source.warehouse_id,
            operation_type_id=source.operation_type_id,
            partner_entity_id=source.partner_entity_id,
            owner_entity_id=source.owner_entity_id,
            name=await cls._seq_name(scope, prefix),
            state=StockTransferState.CONFIRMED,
            scheduled_at=source.scheduled_at,
            origin_document_type=source.origin_document_type,
            origin_document_id=source.origin_document_id,
            backorder_of_id=source.transfer_id,
            created_at=now,
            updated_at=now,
        )
        _ = await cls.objects.create(instance=backorder)
        for posted in residual_posts:
            move = posted.move
            residual = move.product_qty - posted.done_qty
            if residual <= STOCK_ZERO:
                continue
            product = await StockProduct.by_id(company_id, move.product_id)
            doc_qty = (
                await UnitOfMeasure.convert(
                    residual, product.uom_id, move.uom_id
                )
                if product is not None
                else residual
            )
            _ = await StockMove.objects.create(
                instance=StockMove(
                    move_id=new_id("mov"),
                    company_id=company_id,
                    warehouse_id=source.warehouse_id,
                    transfer_id=backorder.transfer_id,
                    product_id=move.product_id,
                    product_qty=residual,
                    product_uom_qty=doc_qty,
                    uom_id=move.uom_id,
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    state=StockMoveState.CONFIRMED,
                    operation_type_id=move.operation_type_id,
                    origin_document_type=move.origin_document_type,
                    origin_document_id=move.origin_document_id,
                    unit_price=move.unit_price,
                    priority=move.priority,
                    date=now,
                    date_deadline=move.date_deadline,
                    created_at=now,
                )
            )
        return backorder

    # --- Команды леджера: граница транзакции = полоса склада ---

    @classmethod
    async def _run_in_warehouse_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        idempotency_key: str,
        command_type: str,
        actor_user_id: str,
        body: Callable[[LaneScope], Awaitable[LaneOutcome[Self]]],
    ) -> LaneRun[Self]:
        """Определить полосу сериализации по складу документа.

        Все команды документа исполняются в одной полосе склада —
        поэтому сначала читаем шапку без блокировки (решаем, какая
        полоса), а потом захватываем её для реальной работы.
        """
        transfer = await cls.by_id(company_id, transfer_id)
        if transfer is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        return await run_in_lanes(
            [stock_warehouse_lane(company_id, transfer.warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def create_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        operation_type_id: str,
        name_prefix: str,
        partner_entity_id: str | None,
        owner_entity_id: str | None,
        scheduled_at: datetime | None,
        origin_document_type: str | None,
        origin_document_id: str | None,
        barcode: str | None,
        moves: list[StockMoveSpec],
        priority: int = 0,
        date_deadline: datetime | None = None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Команда «зарегистрировать накладную» — шапка + строки одним коммитом.

        Создаёт черновик документа и draft-строки по спецификациям.
        Номер ``WH/IN/00042`` берётся из no-gap курсора в той же
        транзакции — номера документов не «горят» при откатах.

        Единицы измерения: пользователь пишет в удобных единицах
        документа («3 коробки»), а движок считает в базовых единицах
        товара («36 шт»). ``product_uom_qty``/``uom_id`` хранят
        документное количество, ``product_qty`` — уже конвертированный
        спрос в базовых единицах; дальше по документу работает только
        он.
        """

        async def body(scope: LaneScope) -> LaneOutcome[Self]:
            now = utcnow()
            transfer = await cls.create(
                cls(
                    transfer_id=new_id("trf"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    operation_type_id=operation_type_id,
                    partner_entity_id=partner_entity_id,
                    owner_entity_id=owner_entity_id,
                    name=await cls._seq_name(scope, name_prefix),
                    state=StockTransferState.DRAFT,
                    scheduled_at=scheduled_at,
                    origin_document_type=origin_document_type,
                    origin_document_id=origin_document_id,
                    priority=priority,
                    date_deadline=date_deadline,
                    created_at=now,
                    updated_at=now,
                )
            )
            if barcode is not None:
                _ = await StockBarcodeIndex.bind(
                    company_id=company_id,
                    barcode=barcode,
                    entity_type=StockBarcodeEntityType.TRANSFER,
                    entity_id=transfer.transfer_id,
                )
            for spec in moves:
                location_id = spec.location_id
                location_dest_id = spec.location_dest_id
                if location_id is None or location_dest_id is None:
                    raise PlatformConflictError(
                        "Move requires location_id/location_dest_id",
                        error_code="move_locations_missing",
                    )
                product = await StockProduct.by_id(company_id, spec.product_id)
                if product is None:
                    raise PlatformNotFoundError(
                        "Product not found", error_code="product_not_found"
                    )
                spec_uom = await UnitOfMeasure.by_id(company_id, spec.uom_id)
                if spec_uom is None:
                    raise PlatformNotFoundError(
                        "Unit of measure not found", error_code="uom_not_found"
                    )
                if (
                    spec_uom.product_id is not None
                    and spec_uom.product_id != spec.product_id
                ):
                    raise PlatformConflictError(
                        "Packaging uom belongs to another product",
                        error_code="uom_product_mismatch",
                    )
                product_qty = await UnitOfMeasure.convert(
                    spec.product_qty, spec.uom_id, product.uom_id
                )
                if spec.route_id is not None:
                    # Маршрутная строка разворачивается в цепочку плеч:
                    # приёмка→QC→хранение — три связанных move.
                    await cls._create_route_chain(
                        company_id=company_id,
                        transfer=transfer,
                        spec=spec,
                        product_qty=product_qty,
                        base_warehouse_id=warehouse_id,
                        base_location_id=location_id,
                        base_location_dest_id=location_dest_id,
                        origin_document_type=origin_document_type,
                        origin_document_id=origin_document_id,
                        priority=priority,
                        date_deadline=date_deadline,
                        now=now,
                    )
                    continue
                _ = await StockMove.create(
                    StockMove(
                        move_id=new_id("mov"),
                        company_id=company_id,
                        warehouse_id=warehouse_id,
                        transfer_id=transfer.transfer_id,
                        product_id=spec.product_id,
                        product_qty=product_qty,
                        product_uom_qty=spec.product_qty,
                        uom_id=spec.uom_id,
                        location_id=location_id,
                        location_dest_id=location_dest_id,
                        state=StockMoveState.DRAFT,
                        operation_type_id=operation_type_id,
                        origin_document_type=origin_document_type,
                        origin_document_id=origin_document_id,
                        unit_price=spec.unit_price,
                        priority=spec.priority if spec.priority is not None else priority,
                        date=now,
                        date_deadline=spec.date_deadline or date_deadline,
                        created_at=now,
                    )
                )
            return LaneOutcome(result=transfer, events=[])

        return await run_in_lanes(
            [stock_warehouse_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def confirm_in_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        reserve: bool,
        dest_overrides: dict[str, str],
        decisions: list[StockDecision],
        removal_strategies: dict[str, StockRemovalStrategy] | None = None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Команда «подтвердить накладную» — все строки → ``confirmed``.

        При ``reserve=True`` (политика типа операции «резервировать сразу»)
        тут же раскладываем резерв по каждому move — с применением
        решений putaway-рефлекса (``dest_overrides``/``decisions``
        записываются в stock_decisions до строк — для аудита «кто и
        почему выбрал эту ячейку»).
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            transfer = await cls._require_locked(company_id, transfer_id)
            for decision in decisions:
                _ = await StockDecision.objects.create(instance=decision)
            moves = await StockMove.list_for_transfer_by_created_at_asc(company_id, transfer_id)
            for listed in moves:
                move = await StockMove.by_id_locked(company_id, listed.move_id)
                if move is None:
                    continue
                _ = await StockMove.confirm_step(company_id=company_id, move=move)
                # Спящее плечо цепочки (waiting) не резервируем — его
                # разбудит advance_chain после проводки предыдущего.
                if reserve and move.state != StockMoveState.WAITING:
                    _ = await StockMove.reserve_step(
                        company_id=company_id,
                        move=move,
                        dest_location_id=dest_overrides.get(move.move_id),
                        owner_entity_id=transfer.owner_entity_id,
                        removal_strategy=(
                            (removal_strategies or {}).get(
                                move.move_id, StockRemovalStrategy.FIFO
                            )
                        ),
                    )
            _ = await cls.refresh_state(company_id, transfer_id)
            fresh = await cls.by_id_locked(company_id, transfer_id)
            assert fresh is not None
            return LaneOutcome(result=fresh, events=[])

        return await cls._run_in_warehouse_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            body=body,
        )

    @classmethod
    async def assign_in_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        dest_overrides: dict[str, str],
        decisions: list[StockDecision],
        removal_strategies: dict[str, StockRemovalStrategy] | None = None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Команда «разложить резерв» — по всем открытым строкам документа.

        По каждому move вызывается reserve_step: quant'ы источника
        получают ``reserved_quantity``, появляются строки исполнения.
        Putaway-решения (куда класть приход) применяются как
        ``dest_overrides`` к шапкам move. Строки done/cancel
        пропускаются — документ может быть частично исполнен.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            transfer = await cls._require_locked(company_id, transfer_id)
            for decision in decisions:
                _ = await StockDecision.objects.create(instance=decision)
            moves = await StockMove.list_for_transfer_by_created_at_asc(company_id, transfer_id)
            for listed in moves:
                move = await StockMove.by_id_locked(company_id, listed.move_id)
                if move is None or move.state in {
                    StockMoveState.DONE,
                    StockMoveState.CANCEL,
                    # Плечо цепочки спит до исполнения предыдущего —
                    # его разбудит advance_chain в свой полосе склада.
                    StockMoveState.WAITING,
                }:
                    continue
                _ = await StockMove.reserve_step(
                    company_id=company_id,
                    move=move,
                    dest_location_id=dest_overrides.get(move.move_id),
                    owner_entity_id=transfer.owner_entity_id,
                    removal_strategy=(
                        (removal_strategies or {}).get(
                            move.move_id, StockRemovalStrategy.FIFO
                        )
                    ),
                )
            _ = await cls.refresh_state(company_id, transfer_id)
            fresh = await cls.by_id_locked(company_id, transfer_id)
            assert fresh is not None
            return LaneOutcome(result=fresh, events=[])

        return await cls._run_in_warehouse_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            body=body,
        )

    @classmethod
    async def validate_in_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        reserve_dests: dict[str, str],
        decisions: list[StockDecision],
        removal_strategies: dict[str, StockRemovalStrategy] | None = None,
        backorder_policy: BackorderPolicy,
        operation_code: str | None,
        create_backorder: bool = True,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
        causation_id: str | None = None,
    ) -> LaneRun[Self]:
        """Команда «исполнить накладную» — провести все строки и закрыть долг.

        По каждому открытому move — ``post_step``: остатки quant,
        резервы и проводки оценки записываются одной транзакцией. Если
        исполнилось не всё количество, по политике типа операции:

        * ``always`` — остаток автоматом уходит в новый transfer-
          backorder («должок поставим позже»);
        * ``never`` — остаток просто сгорает (отказ от недопоставки);
        * ``ask`` — решение у вызывающего: ``create_backorder``
          (Odoo-дефолт — создавать долг).

        События ``stock/move/done`` и ``stock/quant/changed`` уходят в
        LaneCommit — публикуются только после успешного коммита, как
        гарантированное уведомление «факт произошёл».
        """

        async def body(scope: LaneScope) -> LaneOutcome[Self]:
            transfer = await cls._require_locked(company_id, transfer_id)
            for decision in decisions:
                _ = await StockDecision.objects.create(instance=decision)
            moves = await StockMove.list_for_transfer_by_created_at_asc(company_id, transfer_id)
            posted_moves: list[PostedMove] = []
            for listed in moves:
                if listed.state not in {
                    StockMoveState.CONFIRMED,
                    StockMoveState.PARTIALLY_AVAILABLE,
                    StockMoveState.ASSIGNED,
                    StockMoveState.WAITING,
                }:
                    continue
                move = await StockMove.by_id_locked(company_id, listed.move_id)
                if move is None:
                    continue
                if move.state == StockMoveState.WAITING:
                    continue
                posted = await StockMove.post_step(
                    company_id=company_id,
                    move=move,
                    warehouse_id=transfer.warehouse_id,
                    owner_entity_id=transfer.owner_entity_id,
                    reserve_dest=reserve_dests.get(move.move_id),
                    removal_strategy=(
                        (removal_strategies or {}).get(
                            move.move_id, StockRemovalStrategy.FIFO
                        )
                    ),
                    actor_user_id=actor_user_id,
                )
                posted_moves.append(posted)
            backorder: Self | None = None
            residual = [
                posted
                for posted in posted_moves
                if posted.move.product_qty - posted.done_qty > STOCK_ZERO
            ]
            wants_backorder = (
                backorder_policy == BackorderPolicy.ALWAYS
                or (
                    backorder_policy == BackorderPolicy.ASK
                    and create_backorder
                )
            )
            if residual and wants_backorder:
                backorder = await cls._create_backorder(
                    company_id=company_id,
                    scope=scope,
                    source=transfer,
                    residual_posts=residual,
                )
            final_state = await cls.refresh_state(company_id, transfer_id)
            events: list[PlatformEvent] = []
            for posted in posted_moves:
                if not posted.done_now:
                    continue
                events.append(
                    move_done_event(
                        posted,
                        company_id=company_id,
                        warehouse_id=transfer.warehouse_id,
                        operation_code=operation_code,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                    )
                )
                events.extend(
                    quant_changed_events(
                        posted.quants,
                        company_id=company_id,
                        move_id=posted.move.move_id,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                    )
                )
            # Событие «накладная исполнена» — один раз, при переходе
            # состояния в done; повторная валидация уже закрытого
            # документа новым ключом не дублирует уведомление.
            if (
                final_state == StockTransferState.DONE
                and transfer.state != StockTransferState.DONE
            ):
                events.append(
                    company_event(
                        STOCK_TRANSFER_DONE,
                        StockTransferDonePayload(
                            company_id=company_id,
                            transfer_id=transfer.transfer_id,
                            warehouse_id=transfer.warehouse_id,
                            operation_type_id=transfer.operation_type_id,
                            operation_code=operation_code,
                            name=transfer.name,
                            partner_entity_id=transfer.partner_entity_id,
                            backorder_of_id=transfer.backorder_of_id,
                            return_of_id=transfer.return_of_id,
                            backorder_transfer_id=(
                                backorder.transfer_id
                                if backorder is not None
                                else None
                            ),
                            move_ids=[
                                posted.move.move_id for posted in posted_moves
                            ],
                            origin_document_type=transfer.origin_document_type,
                            origin_document_id=transfer.origin_document_id,
                            done_at=utcnow().isoformat(),
                        ),
                        company_id=company_id,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                    )
                )
            fresh = await cls.by_id_locked(company_id, transfer_id)
            assert fresh is not None
            return LaneOutcome(result=fresh, events=events)

        return await cls._run_in_warehouse_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            body=body,
        )

    @classmethod
    async def cancel_in_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Команда «аннулировать накладную» — все её строки отменяются.

        Бухгалтерский принцип: проведённую строку сторнировать нельзя —
        только обратный документ. Поэтому если хоть один move уже
        ``done``, весь документ отменить нельзя (``transfer_done``):
        расхождение закрывается возвратом, а не «стиранием» истории.
        Черновые/резервные строки отменяются, резерв возвращается в
        доступное.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            _ = await cls._require_locked(company_id, transfer_id)
            moves = await StockMove.list_for_transfer_by_created_at_asc(company_id, transfer_id)
            for listed in moves:
                if listed.state == StockMoveState.DONE:
                    raise PlatformConflictError(
                        "Done transfer cannot be cancelled",
                        error_code="transfer_done",
                    )
            for listed in moves:
                if listed.state == StockMoveState.CANCEL:
                    continue
                move = await StockMove.by_id_locked(company_id, listed.move_id)
                if move is None:
                    continue
                _ = await StockMove.cancel_step(company_id=company_id, move=move)
            _ = await cls.refresh_state(company_id, transfer_id)
            fresh = await cls.by_id_locked(company_id, transfer_id)
            assert fresh is not None
            return LaneOutcome(result=fresh, events=[])

        return await cls._run_in_warehouse_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            body=body,
        )

    @classmethod
    async def unreserve_move_in_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        move_id: str,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Команда «снять резерв с одной строки» — товар свободен для других.

        Точечный unreserve: release_step по указанному move, строка
        возвращается в ``confirmed``. Остальные строки накладной не
        тронуты. Проекция состояния документа пересчитывается.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            _ = await cls._require_locked(company_id, transfer_id)
            move = await StockMove.by_id_locked(company_id, move_id)
            if move is None or move.transfer_id != transfer_id:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            _ = await StockMove.release_step(company_id=company_id, move=move)
            if move.state in {
                StockMoveState.ASSIGNED,
                StockMoveState.PARTIALLY_AVAILABLE,
            }:
                _ = await StockMove.write_state(
                    company_id, move, StockMoveState.CONFIRMED
                )
            _ = await cls.refresh_state(company_id, transfer_id)
            fresh = await cls.by_id_locked(company_id, transfer_id)
            assert fresh is not None
            return LaneOutcome(result=fresh, events=[])

        return await cls._run_in_warehouse_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            body=body,
        )

    @classmethod
    async def return_in_lane(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        move_quantities: dict[str, Decimal] | None,
        operation_code: str | None,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
        causation_id: str | None = None,
    ) -> LaneRun[Self]:
        """Команда «оформить возврат» — обратная накладная + reversed-строки.

        Возврат — не удаление исходного документа, а новый transfer с
        ``return_of_id`` на него: по каждой проведённой строке создаётся
        зеркальный move (location_id ↔ location_dest_id поменялись
        местами, ``returned_move_id`` — ссылка на оригинал). Номер —
        ``WH/IN/00042/RET/00001``.

        Можно вернуть частично: ``move_quantities`` ограничивает
        количество по строкам (вернули 2 из 5). Потолок — фактически
        доставленное минус уже возвращённое ранее по этой строке;
        запрос больше остатка — ``return_quantity_exceeded``: вернуть
        «больше, чем ушло» означало бы напечатать товар и деньги из
        воздуха. Оценка возврата идёт по себестоимости исходного move —
        деньги «откатываются» ровно на ту сумму, на которую товар
        ушёл/пришёл.

        Весь цикл create→confirm→reserve→post исполняется одной
        полосой — возврат либо проведён целиком, либо не существует.
        """

        async def body(scope: LaneScope) -> LaneOutcome[Self]:
            source = await cls._require_locked(company_id, transfer_id)
            moves = await StockMove.list_for_transfer_by_created_at_asc(company_id, transfer_id)
            done_moves = [
                move for move in moves if move.state == StockMoveState.DONE
            ]
            if not done_moves:
                raise PlatformConflictError(
                    "Only done transfers can be returned",
                    error_code="transfer_not_done",
                )
            now = utcnow()
            head = source.name.rsplit("/", 1)[0]
            back = await cls.create(
                cls(
                    transfer_id=new_id("trf"),
                    company_id=company_id,
                    warehouse_id=source.warehouse_id,
                    operation_type_id=source.operation_type_id,
                    partner_entity_id=source.partner_entity_id,
                    owner_entity_id=source.owner_entity_id,
                    name=await cls._seq_name(scope, f"{head}/RET"),
                    state=StockTransferState.DRAFT,
                    scheduled_at=source.scheduled_at,
                    origin_document_type=source.origin_document_type,
                    origin_document_id=source.origin_document_id,
                    return_of_id=transfer_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            posted_moves: list[PostedMove] = []
            for move in done_moves:
                # Вернуть можно только то, что реально доставлено: сумма
                # done по проведённым строкам (product_uom_qty — ЗАКАЗ,
                # частичная проводка его не уменьшает) минус уже
                # возвращённое ранее этой же строкой — серия частичных
                # возвратов суммарно не может превысить факт отгрузки.
                delivered = sum(
                    (
                        line.done_quantity
                        for line in await StockMoveLine.list_for_move_by_created_at_asc(
                            company_id, move.move_id
                        )
                        if line.state == StockMoveLineState.DONE
                    ),
                    STOCK_ZERO,
                )
                already_returned = STOCK_ZERO
                for ret in await StockMove.objects.filter(
                    company_id=company_id, returned_move_id=move.move_id
                ).all():
                    if ret.state == StockMoveState.CANCEL:
                        continue
                    already_returned += sum(
                        (
                            line.done_quantity
                            for line in await StockMoveLine.list_for_move_by_created_at_asc(
                                company_id, ret.move_id
                            )
                            if line.state == StockMoveLineState.DONE
                        ),
                        STOCK_ZERO,
                    )
                returnable = delivered - already_returned
                qty = (
                    move_quantities.get(move.move_id)
                    if move_quantities is not None
                    else returnable
                )
                if qty is None or qty <= STOCK_ZERO:
                    continue
                if qty > returnable:
                    raise PlatformConflictError(
                        "Return quantity exceeds what was delivered",
                        error_code="return_quantity_exceeded",
                    )
                new_move = await StockMove.create(
                    StockMove(
                        move_id=new_id("mov"),
                        company_id=company_id,
                        warehouse_id=source.warehouse_id,
                        transfer_id=back.transfer_id,
                        product_id=move.product_id,
                        product_qty=qty,
                        product_uom_qty=qty,
                        uom_id=move.uom_id,
                        location_id=move.location_dest_id,
                        location_dest_id=move.location_id,
                        state=StockMoveState.DRAFT,
                        operation_type_id=move.operation_type_id,
                        origin_document_type=move.origin_document_type,
                        origin_document_id=move.origin_document_id,
                        returned_move_id=move.move_id,
                        unit_price=move.unit_price,
                        priority=move.priority,
                        date=now,
                        date_deadline=move.date_deadline,
                        created_at=now,
                    )
                )
                _ = await StockMove.confirm_step(
                    company_id=company_id, move=new_move
                )
                # Возврат трассируемого товара из внешнего источника
                # (клиент вернул партию/серийник): reserve_step создал бы
                # безликую строку, а проводка требует lot_id. Зеркалим
                # проведённые строки оригинала: те же партии, в том же
                # порядке, пока хватает количества.
                product = await StockProduct.by_id(
                    company_id, move.product_id
                )
                src_loc = await StockLocation.by_id(
                    company_id, new_move.location_id
                )
                mirrored = False
                if (
                    product is not None
                    and product.tracking != StockTracking.NONE
                    and src_loc is not None
                    and src_loc.usage in STOCK_EXTERNAL_USAGES
                ):
                    mirrored = await cls._mirror_return_lines(
                        company_id,
                        new_move,
                        move,
                        qty,
                        back.owner_entity_id,
                    )
                if not mirrored:
                    _ = await StockMove.reserve_step(
                        company_id=company_id,
                        move=new_move,
                        dest_location_id=None,
                        owner_entity_id=back.owner_entity_id,
                    )
                posted = await StockMove.post_step(
                    company_id=company_id,
                    move=new_move,
                    warehouse_id=source.warehouse_id,
                    owner_entity_id=back.owner_entity_id,
                    actor_user_id=actor_user_id,
                )
                posted_moves.append(posted)
            _ = await cls.refresh_state(company_id, back.transfer_id)
            events: list[PlatformEvent] = []
            for posted in posted_moves:
                if not posted.done_now:
                    continue
                events.append(
                    move_done_event(
                        posted,
                        company_id=company_id,
                        warehouse_id=source.warehouse_id,
                        operation_code=operation_code,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                    )
                )
                events.extend(
                    quant_changed_events(
                        posted.quants,
                        company_id=company_id,
                        move_id=posted.move.move_id,
                        actor_user_id=actor_user_id,
                        causation_id=causation_id,
                    )
                )
            fresh = await cls.by_id_locked(company_id, back.transfer_id)
            assert fresh is not None
            return LaneOutcome(result=fresh, events=events)

        return await cls._run_in_warehouse_lane(
            company_id=company_id,
            transfer_id=transfer_id,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            body=body,
        )

    @classmethod
    async def _mirror_return_lines(
        cls,
        company_id: str,
        new_move: StockMove,
        origin_move: StockMove,
        qty: Decimal,
        owner_entity_id: str | None,
    ) -> bool:
        """Зеркальные строки возврата с партиями оригинальной отгрузки.

        Клиент возвращает те самые партии/серийники, что получил, —
        строка исполнения возврата обязана нести ``lot_id`` исходной
        проводки: ``_check_tracking`` на приёмнике-ячейке требует
        трассировку, а безликая строка сделала бы складской остаток
        неотслеживаемым (и просто упала бы с ``lot_required``).

        Раскладка жадная по проведённым строкам оригинала в порядке
        их создания: возвращаемое количество «откусывается» от каждой
        до покрытия ``qty``. Для серийника каждая исходная строка ≤ 1
        шт — частичный возврат берёт первые серийники по очереди;
        выбор конкретного SN на возврат — дело документа-заявки.

        Возвращает False, когда зеркалить нечего (нет проведённых
        строк с партиями) — тогда идём обычным ``reserve_step``.
        """
        origin_lines = await StockMoveLine.list_for_move_by_created_at_asc(
            company_id, origin_move.move_id
        )
        done_lines = [
            line
            for line in origin_lines
            if line.state == StockMoveLineState.DONE
            and line.kind == StockMoveLineKind.QUANTITY
            and line.lot_id is not None
            and line.done_quantity > STOCK_ZERO
        ]
        if not done_lines:
            return False
        dst = await StockLocation.by_id(company_id, new_move.location_dest_id)
        walk_sequence = dst.pick_sequence if dst is not None else 0
        remaining = qty
        now = utcnow()
        for origin_line in done_lines:
            if remaining <= STOCK_ZERO:
                break
            take = min(origin_line.done_quantity, remaining)
            _ = await StockMoveLine.objects.create(
                instance=StockMoveLine(
                    move_line_id=new_id("mli"),
                    company_id=company_id,
                    move_id=new_move.move_id,
                    transfer_id=new_move.transfer_id,
                    warehouse_id=new_move.warehouse_id,
                    product_id=new_move.product_id,
                    lot_id=origin_line.lot_id,
                    owner_entity_id=owner_entity_id,
                    quantity=take,
                    done_quantity=take,
                    location_id=new_move.location_id,
                    location_dest_id=new_move.location_dest_id,
                    priority=new_move.priority,
                    sequence=walk_sequence,
                    created_at=now,
                )
            )
            remaining -= take
        if remaining > STOCK_ZERO:
            # Зеркал покрыл не всё — не должно случаться при капе
            # returnable ≤ delivered, но подстрахуемся: хвост добираем
            # безликой строкой, проводка её отклонит для tracked.
            _ = await StockMoveLine.objects.create(
                instance=StockMoveLine(
                    move_line_id=new_id("mli"),
                    company_id=company_id,
                    move_id=new_move.move_id,
                    transfer_id=new_move.transfer_id,
                    warehouse_id=new_move.warehouse_id,
                    product_id=new_move.product_id,
                    owner_entity_id=owner_entity_id,
                    quantity=remaining,
                    done_quantity=remaining,
                    location_id=new_move.location_id,
                    location_dest_id=new_move.location_dest_id,
                    priority=new_move.priority,
                    sequence=walk_sequence,
                    created_at=now,
                )
            )
        _ = await StockMove.write_state(
            company_id, new_move, StockMoveState.ASSIGNED
        )
        return True

    @classmethod
    async def _require_locked(cls, company_id: str, transfer_id: str) -> Self:
        transfer = await cls.by_id_locked(company_id, transfer_id)
        if transfer is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        return transfer

    @classmethod
    async def _create_route_chain(
        cls,
        *,
        company_id: str,
        transfer: Self,
        spec: StockMoveSpec,
        product_qty: Decimal,
        base_warehouse_id: str,
        base_location_id: str,
        base_location_dest_id: str,
        origin_document_type: str | None,
        origin_document_id: str | None,
        priority: int,
        date_deadline: datetime | None,
        now: datetime,
    ) -> None:
        """Развернуть строку накладной в цепочку плеч по шагам маршрута (pull).

        Бизнес-сценарий «приёмка → контроль качества → хранение»: одна
        строка документа порождает три связанных ``move``. Первое плечо
        создаётся ``draft`` — его подтверждает обычный ``confirm``;
        последующие спят в ``waiting``, пока предыдущее плечо не
        станет ``done`` — тогда ``advance_chain`` будит их в
        ``confirmed`` и резервирует под своей полосой склада.

        Границы плеч:
          * источник первого плеча — явный ``spec.location_id``, иначе
            дефолт типа операции шага;
          * приёмник плеча i — явный ``dest_location_id`` шага, иначе
            источник следующего шага (рукопожатие плеч), иначе дефолт
            типа операции;
          * приёмник последнего — ``spec.location_dest_id``.
        Склад плеча — склад его типа операции (межскладская цепочка
        пройдёт через транзитную локацию и шаг с типом операции другого
        склада).
        """
        assert spec.route_id is not None
        route = await StockRoute.by_id(company_id, spec.route_id)
        if route is None or not route.is_active:
            raise PlatformNotFoundError(
                "Route not found", error_code="route_not_found"
            )
        steps = sorted(route.steps, key=lambda s: s.sequence)
        if not steps:
            raise PlatformConflictError(
                "Route has no steps", error_code="route_empty"
            )
        op_types: dict[str, StockOperationType] = {}
        for step in steps:
            ot = op_types.get(step.operation_type_id)
            if ot is None:
                found = await StockOperationType.by_id(
                    company_id, step.operation_type_id
                )
                if found is None:
                    raise PlatformNotFoundError(
                        "Route step operation type not found",
                        error_code="operation_type_not_found",
                    )
                op_types[step.operation_type_id] = found
                ot = found
        prev: StockMove | None = None
        last = len(steps) - 1
        for idx, step in enumerate(steps):
            ot = op_types[step.operation_type_id]
            src = (
                step.source_location_id
                or (prev.location_dest_id if prev is not None else base_location_id)
                or ot.default_source_location_id
            )
            if idx == last:
                dst = step.dest_location_id or base_location_dest_id
            else:
                nxt_ot = op_types[steps[idx + 1].operation_type_id]
                dst = (
                    step.dest_location_id
                    or steps[idx + 1].source_location_id
                    or nxt_ot.default_source_location_id
                    or ot.default_dest_location_id
                )
            if src is None or dst is None:
                raise PlatformConflictError(
                    "Route step cannot resolve source/destination",
                    error_code="move_locations_missing",
                )
            move = await StockMove.create(
                StockMove(
                    move_id=new_id("mov"),
                    company_id=company_id,
                    warehouse_id=ot.warehouse_id or base_warehouse_id,
                    transfer_id=transfer.transfer_id,
                    product_id=spec.product_id,
                    product_qty=product_qty,
                    product_uom_qty=spec.product_qty,
                    uom_id=spec.uom_id,
                    location_id=src,
                    location_dest_id=dst,
                    state=(
                        StockMoveState.DRAFT
                        if prev is None
                        else StockMoveState.WAITING
                    ),
                    operation_type_id=step.operation_type_id,
                    origin_document_type=origin_document_type,
                    origin_document_id=origin_document_id,
                    route_id=spec.route_id,
                    move_origin_id=prev.move_id if prev is not None else None,
                    unit_price=spec.unit_price,
                    priority=(
                        spec.priority if spec.priority is not None else priority
                    ),
                    date=now,
                    date_deadline=spec.date_deadline or date_deadline,
                    created_at=now,
                )
            )
            if prev is not None:
                _ = await StockMove.objects.filter(
                    company_id=company_id, move_id=prev.move_id
                ).update(using=STOCK_DB, move_dest_id=move.move_id)
            prev = move

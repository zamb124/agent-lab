"""ScanService — связка «скан → шаг машины → атомарная проводка».

Терминал сбора данных (ТСД) работает сессиями: оператор сканирует
коды, каждый скан продвигает чистую машину ``models/scan.py``, а
финальный ``commit`` одной транзакцией в полосе склада материализует
набранное в строки движения, проводку остатков и слои оценки.

Контракт сервиса:

* ``resolve`` — «что за штрихкод»: индекс штрихкодов + GS1-семантика
  (GTIN+партия → LOT, SSCC → контейнер, фасовка → её товар и кратность);
* ``step``/``quantity`` — чистые переходы машины (контекст приезжает
  от клиента и возвращается ему — сервис не держит сессий);
* ``commit`` — ``StockMove.post_lines_in_lane``: сплит резервных
  строк, проводка quant'ов, слои стоимости, события после commit.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from pydantic import BaseModel

from apps.stock.models import (
    STOCK_QUANT_USAGES,
    StockBarcodeEntityType,
    StockLocation,
    StockLocationUsage,
    StockLot,
    StockMove,
    StockMoveLine,
    StockMoveLineKind,
    StockMoveState,
    StockOperationCode,
    StockOperationType,
    StockProduct,
    StockQuant,
    StockTracking,
    StockTransfer,
    StockTransferState,
)
from apps.stock.models.common import (
    STOCK_DB,
    STOCK_ZERO,
    StockMoveSpec,
    new_id,
    stock_command_lane,
)
from apps.stock.models.scan import (
    ScanContext,
    ScanEntityKind,
    ScanError,
    ScanFlow,
    ScanLineDraft,
    ScanResolution,
    ScanStepResult,
    scan_commit_ready,
    scan_quantity,
    scan_step,
)
from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.move_engine import StockMoveEngine
from core.catalog.models import CatalogProduct, CatalogUom
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import (
    LaneOutcome,
    LaneScope,
    publish_lane_run,
    run_in_lanes,
)
from core.request_scope import command_idempotency_key
from core.tracing.attributes import ATTR_TENANT_COMPANY_ID
from core.tracing.operation_span import traced_operation
from core.utils.time import utcnow


class _QuantIds(BaseModel):
    ids: list[str]

_ENTITY_KIND = {
    StockBarcodeEntityType.PRODUCT: ScanEntityKind.PRODUCT,
    StockBarcodeEntityType.PACKAGING: ScanEntityKind.PACKAGING,
    StockBarcodeEntityType.LOCATION: ScanEntityKind.LOCATION,
    StockBarcodeEntityType.CONTAINER: ScanEntityKind.CONTAINER,
    StockBarcodeEntityType.LOT: ScanEntityKind.LOT,
    StockBarcodeEntityType.TRANSFER: ScanEntityKind.DOCUMENT,
    StockBarcodeEntityType.RESOURCE: ScanEntityKind.RESOURCE,
}
"""Тип носителя индекса → тип сущности скан-машины."""

_LOCATION_ENTITIES = frozenset(
    {ScanEntityKind.LOCATION, ScanEntityKind.CONTAINER}
)
"""Сущности скана, разворачивающиеся в строку ``stock_locations``."""


def _location_slots(ctx: ScanContext) -> frozenset[str]:
    """Id локаций, уже лежащие в слотах контекста."""
    return frozenset(
        slot
        for slot in (ctx.source_id, ctx.dest_id, ctx.container_id)
        if slot is not None
    )


class ScanService:
    """Шаги и коммит скан-сессии ТСД."""

    def __init__(
        self,
        barcode_service: BarcodeService,
        move_engine: StockMoveEngine,
    ) -> None:
        self._barcode: BarcodeService = barcode_service
        self._moves: StockMoveEngine = move_engine

    async def resolve(
        self, *, company_id: str, barcode: str
    ) -> ScanResolution:
        """«Что это за код» — индекс + GS1 + доменные связи.

        Ответ не просто «партия LOT-7», а контекст для машины: у партии
        подмешан её товар, у фасовки — товар и кратность («короб 24»),
        у GS1-кода — серия/количество из AI.
        """
        result = await self._barcode.resolve(company_id=company_id, barcode=barcode)
        kind = _ENTITY_KIND[result.entity_type]
        parsed = result.parsed
        resolution = ScanResolution(
            entity_kind=kind,
            entity_id=result.entity_id,
            barcode=barcode,
            serial=parsed.serial,
            quantity=parsed.quantity or parsed.weight_kg,
        )
        if kind == ScanEntityKind.LOT:
            lot = await StockLot.by_id(company_id, result.entity_id)
            if lot is not None:
                # Скан серийника — это всегда ровно одна штука:
                # «ввести 1» на каждом SN — лишний жест оператора.
                product = await StockProduct.by_id(
                    company_id, lot.product_id
                )
                resolution = replace(
                    resolution,
                    product_id=lot.product_id,
                    lot_id=lot.lot_id,
                    quantity=(
                        Decimal("1")
                        if product is not None
                        and product.tracking == StockTracking.SERIAL
                        else resolution.quantity
                    ),
                )
        elif kind == ScanEntityKind.PACKAGING:
            # Упаковка — AUoM: строка catalog_uoms с product_id; количество
            # базовых единиц = factor / factor(базовой ЕИ товара).
            uom = await CatalogUom.by_id(company_id, result.entity_id)
            product = (
                await CatalogProduct.by_id(company_id, uom.product_id)
                if uom is not None and uom.product_id is not None
                else None
            )
            base = (
                await CatalogUom.by_id(company_id, product.uom_id)
                if product is not None
                else None
            )
            if uom is not None and product is not None and base is not None:
                qty = uom.factor / base.factor
                resolution = replace(
                    resolution,
                    product_id=product.product_id,
                    packaging_id=uom.uom_id,
                    packaging_qty=qty,
                    quantity=resolution.quantity or qty,
                )
        return resolution

    @staticmethod
    def _executable_lines(
        lines: list[StockMoveLine], user_id: str
    ) -> list[StockMoveLine]:
        """Строки, которые этот оператор реально исполнит: свободные
        или уже закреплённые за ним. Чужой claim — не его работа."""
        return [
            line
            for line in lines
            if line.assigned_user_id in {None, user_id}
        ]

    async def first_executable_line(
        self,
        *,
        company_id: str,
        move_id: str,
        user_id: str,
    ) -> StockMoveLine | None:
        """Первая исполнимая строка документа — подсказка экрану.

        ``done_quantity`` открытой строки — сколько оператору взять
        (подсказка кладовщику), ``quantity`` — сколько резерва она ещё
        держит: после частичного скан-коммита обе уменьшаются вместе,
        поэтому остаток работы читается из ``done_quantity``.
        ``None`` — работы нет или всё захвачено чужими claim'ами.
        """
        lines = await StockMoveLine.list_open_for_move_by_sequence_created_at_asc(
            company_id, move_id
        )
        executable = self._executable_lines(lines, user_id)
        return executable[0] if executable else None

    async def open_session(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        move_id: str | None,
        transfer_id: str | None,
        user_id: str,
    ) -> tuple[StockMove, ScanContext]:
        """Старт doc-driven сессии: backend выбирает поток по документу.

        Документ диктует экран: ``kind=container`` линий → перевозка тары,
        ``kind=count`` → пересчёт, иначе код типа операции (приёмка →
        ``receive``, отгрузка → ``pick``, внутренняя → ``move``). За
        ``transfer_id`` берётся первый move со строками, которые оператор
        исполнит: целиком захваченный другим документ — не его работа.
        """
        if move_id is not None:
            move = await StockMove.by_id(company_id, move_id)
            if move is None or move.warehouse_id != warehouse_id:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
        elif transfer_id is not None:
            move = None
            # Работу выбираем по первой исполнимой строке в порядке
            # обхода очереди (sequence → created_at): move'ы накладной
            # рождаются пачкой с одним created_at, сортировка по нему
            # недетерминирована.
            moves = [
                m
                for m in await StockMove.list_for_transfer_by_created_at_asc(
                    company_id, transfer_id
                )
                if m.warehouse_id == warehouse_id
            ]
            open_lines = await StockMoveLine.list_open_for_moves_by_sequence_created_at_asc(
                company_id, [m.move_id for m in moves]
            )
            executable = self._executable_lines(open_lines, user_id)
            if executable:
                move = next(
                    m for m in moves if m.move_id == executable[0].move_id
                )
            if move is None:
                raise PlatformNotFoundError(
                    "No open work on document", error_code="document_no_work"
                )
        else:
            raise PlatformConflictError(
                "Pass move_id or transfer_id", error_code="scan_open_input_invalid"
            )
        lines = self._executable_lines(
            await StockMoveLine.list_open_for_move_by_sequence_created_at_asc(
                company_id, move.move_id
            ),
            user_id,
        )
        if not lines:
            raise PlatformNotFoundError(
                "Document has no open work", error_code="document_no_work"
            )
        flow = await self._session_flow(company_id, move, lines[0].kind)
        return move, ScanContext(flow=flow)

    @staticmethod
    async def _session_flow(
        company_id: str, move: StockMove, line_kind: StockMoveLineKind
    ) -> ScanFlow:
        if line_kind == StockMoveLineKind.CONTAINER:
            return ScanFlow.CONTAINER_MOVE
        if line_kind == StockMoveLineKind.COUNT:
            return ScanFlow.COUNT
        if move.operation_type_id is None:
            return ScanFlow.MOVE
        operation_type = await StockOperationType.by_id(
            company_id, move.operation_type_id
        )
        if operation_type is None:
            return ScanFlow.MOVE
        # Явная семантика плеча маршрута побеждает вывод из ``code``:
        # «упаковка» и «отгрузка» — разные экраны ТСД при одном классе.
        if operation_type.scan_flow is not None:
            return operation_type.scan_flow
        match operation_type.code:
            case StockOperationCode.INCOMING:
                return ScanFlow.RECEIVE
            case StockOperationCode.OUTGOING:
                return ScanFlow.PICK
            case _:
                return ScanFlow.MOVE

    async def step(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        context: ScanContext,
        resolution: ScanResolution,
    ) -> ScanStepResult:
        """Один скан: машина + проверка ячейки против склада сессии.

        Ячейка, попавшая в слот (источник, приёмник, тара), обязана
        быть реальной полкой: активной и на quant-usage — иначе скан
        зоны-группировки или виртуальной локации привёл бы остатки на
        место, где физически лежать не может. У ``bin`` сверяется и
        склад: ячейка чужого склада — ошибка оператора. Контейнер и
        transit складом не ограничиваем: тара физически ездит между
        складами, ``warehouse_id`` на ней — административный владелец.
        """
        result = scan_step(context, resolution)
        if (
            result.error is not None
            or resolution.entity_kind not in _LOCATION_ENTITIES
            or resolution.entity_id not in _location_slots(result.context)
        ):
            return result
        location = await StockLocation.by_id(company_id, resolution.entity_id)
        if (
            location is None
            or not location.is_active
            or location.usage not in STOCK_QUANT_USAGES
            or (
                location.usage == StockLocationUsage.BIN
                and location.warehouse_id != warehouse_id
            )
        ):
            return ScanStepResult(
                context=context, error=ScanError.LOCATION_INVALID
            )
        return result

    def quantity(
        self, *, context: ScanContext, quantity: Decimal
    ) -> ScanStepResult:
        """Числовой ввод количества на шаге ``quantity``."""
        return scan_quantity(context, quantity)

    async def commit(
        self,
        *,
        company_id: str,
        move_id: str,
        context: ScanContext,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/scan/commit_requested",
        causation_id: str | None = None,
    ) -> StockMove:
        """Атомарный коммит скан-сессии по одному move.

        Одна транзакция полосы склада: строки контекста → move_lines
        (сплит резерва), проводка остатков, слои оценки, события —
        всё или ничего. Ошибка любой строки откатывает весь коммит.

        Для ``container_move`` move играет роль носителя документа:
        строка ``kind=container`` строится из слотов контекста
        (``container_id`` + ``dest_id``), а не из ``lines``.
        """
        err = scan_commit_ready(context)
        if err is not None:
            raise PlatformConflictError(
                "Scan context has nothing to commit",
                error_code=err.value,
            )
        move = await StockMove.by_id(company_id, move_id)
        if move is None:
            raise PlatformNotFoundError(
                "Move not found", error_code="move_not_found"
            )
        ship_all = context.flow == ScanFlow.SHIP
        if ship_all:
            # Отгрузка без пересканирования позиций — привилегия плеча
            # «ship»: контекст приходит с клиента, право проверяем по
            # типу операции, а не по заявлению контекста.
            operation_type = (
                await StockOperationType.by_id(company_id, move.operation_type_id)
                if move.operation_type_id is not None
                else None
            )
            if operation_type is None or operation_type.scan_flow != ScanFlow.SHIP:
                raise PlatformConflictError(
                    "Move is not executable as a ship leg",
                    error_code="scan_ship_denied",
                )
        container_move: tuple[str, str] | None = None
        if context.container_id is not None and context.dest_id is not None:
            container_move = (context.container_id, context.dest_id)
        async with traced_operation(
            "stock.scan.commit",
            operation_category="stock_mutation",
            resource_type="stock_move",
            resource_id=move.move_id,
            extra_attributes={
                ATTR_TENANT_COMPANY_ID: company_id,
                **(
                    {"stock.warehouse_id": move.warehouse_id}
                    if move.warehouse_id is not None
                    else {}
                ),
                "stock.scan_lines": len(context.lines),
            },
        ):
            run = await StockMove.post_lines_in_lane(
                company_id=company_id,
                move_id=move.move_id,
                warehouse_id=move.warehouse_id,
                drafts=list(context.lines),
                ship_all=ship_all,
                container_move=container_move,
                owner_entity_id=None,
                operation_code=None,
                idempotency_key=command_idempotency_key(idempotency_key),
                actor_user_id=actor_user_id,
                command_type=command_type,
                causation_id=causation_id,
                # Накладная следует за строками в той же транзакции:
                # хук отдан сервису, чтобы модель move не тащила
                # StockTransfer (двунаправленный импорт-цикл).
                on_move_done=StockTransfer.done_event_after_move,
            )
        await publish_lane_run(run, using=STOCK_DB)
        if run.result.state == StockMoveState.DONE and move.transfer_id:
            # Плечо маршрутной цепочки проведено сканером — будим
            # следующее в его собственной полосе склада.
            await self._moves.advance_chains(company_id, move.transfer_id)
        return run.result

    async def commit_adhoc(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        operation_code: StockOperationCode,
        context: ScanContext,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/scan/adhoc_commit_requested",
        causation_id: str | None = None,
    ) -> StockTransfer:
        """Ad-hoc коммит без планового документа — сессия пишет накладную.

        Оператор набрал строки «свободным» потоком (переместил товар,
        принял без наряда): backend группирует их по продукту, создаёт
        накладную с move на каждый продукт и проводит строки тем же
        ``post_lines_in_lane``, что и doc-driven коммит — один факт,
        один леджер, никакой параллельной записи мимо движений.
        """
        err = scan_commit_ready(context)
        if err is not None or not context.lines:
            raise PlatformConflictError(
                "Scan context has nothing to commit",
                error_code=(
                    err.value if err is not None else ScanError.NOTHING_TO_COMMIT.value
                ),
            )
        by_product: dict[str, list[ScanLineDraft]] = {}
        for draft in context.lines:
            by_product.setdefault(draft.product_id, []).append(draft)
        op_types = await StockOperationType.list_for_warehouse_by_code_asc(
            company_id, warehouse_id
        )
        operation_type = next(
            (op for op in op_types if op.code == operation_code), None
        )
        if operation_type is None:
            raise PlatformNotFoundError(
                "Operation type not found", error_code="operation_type_not_found"
            )
        specs: list[StockMoveSpec] = []
        for product_id, product_drafts in by_product.items():
            product = await CatalogProduct.by_id(company_id, product_id)
            if product is None:
                raise PlatformNotFoundError(
                    "Product not found", error_code="product_not_found"
                )
            first = product_drafts[0]
            specs.append(
                StockMoveSpec(
                    product_id=product_id,
                    product_qty=sum(
                        (draft.quantity for draft in product_drafts), STOCK_ZERO
                    ),
                    uom_id=product.uom_id,
                    unit_price=None,
                    location_id=first.location_id,
                    location_dest_id=first.location_dest_id,
                )
            )
        base_key = command_idempotency_key(idempotency_key)
        created = await self._moves.create_transfer(
            company_id=company_id,
            warehouse_id=warehouse_id,
            operation_type_id=operation_type.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=specs,
            idempotency_key=base_key,
            actor_user_id=actor_user_id,
        )
        # Идемпотентный повтор: lane вернул записанный результат первого
        # прогона (draft-снапшот), а фактические строки уже проведены —
        # свежие состояния решают, какие шаги докрутить, а какие пропустить.
        fresh = await StockTransfer.by_id(company_id, created.transfer_id)
        if fresh is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        if fresh.state == StockTransferState.DONE:
            return fresh
        if fresh.state == StockTransferState.DRAFT:
            fresh = await self._moves.confirm_transfer(
                company_id=company_id,
                transfer_id=created.transfer_id,
                idempotency_key=f"{base_key}:confirm",
                actor_user_id=actor_user_id,
            )
        if fresh.state in {
            StockTransferState.CONFIRMED,
            StockTransferState.PARTIALLY_AVAILABLE,
        }:
            fresh = await self._moves.assign_transfer(
                company_id=company_id,
                transfer_id=created.transfer_id,
                idempotency_key=f"{base_key}:assign",
                actor_user_id=actor_user_id,
            )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            company_id, created.transfer_id
        )
        by_move = {move.product_id: move for move in moves}
        for product_id, product_drafts in by_product.items():
            move = by_move[product_id]
            if move.state == StockMoveState.DONE:
                continue
            run = await StockMove.post_lines_in_lane(
                company_id=company_id,
                move_id=move.move_id,
                warehouse_id=move.warehouse_id,
                drafts=list(product_drafts),
                ship_all=False,
                container_move=None,
                owner_entity_id=None,
                operation_code=str(operation_code),
                idempotency_key=f"{base_key}:{product_id}",
                actor_user_id=actor_user_id,
                command_type=command_type,
                causation_id=causation_id,
                on_move_done=StockTransfer.done_event_after_move,
            )
            await publish_lane_run(run, using=STOCK_DB)
        return await self._moves.validate_transfer(
            company_id=company_id,
            transfer_id=created.transfer_id,
            idempotency_key=f"{base_key}:validate",
            actor_user_id=actor_user_id,
        )

    async def inventory_count_commit(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        context: ScanContext,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/scan/count_commit_requested",
    ) -> list[str]:
        """Коммит потока ``count``: факт-строки → черновик подсчёта quant.

        Каждая набранная строка пишет ``inventory_quantity`` на quant
        (ячейка × товар × партия) — расхождение проводится отдельной
        командой ``inventory_apply``, как в бумажной инвентаризации:
        сначала «насчитали», потом «утвердили дельту». Все записи — в
        одной транзакции полосы склада.
        """
        if not context.lines:
            raise PlatformConflictError(
                "Scan count has nothing to commit",
                error_code=ScanError.NOTHING_TO_COMMIT.value,
            )

        async def body(_scope: LaneScope) -> LaneOutcome[_QuantIds]:
            quant_ids: list[str] = []
            count_location_ids = sorted(
                {ln.location_id for ln in context.lines if ln.location_id}
            )
            count_locations = await StockLocation.found_in_company_by_ids(
                company_id, count_location_ids
            )
            for line in context.lines:
                if line.location_id is None:
                    continue
                # Пересчёт допустим только на ячейках, хранящих остаток:
                # «посчитать» зону-view или точку партнёра создало бы
                # фантомный quant на локации без физического стока.
                location = count_locations.get(line.location_id)
                if location is None:
                    raise PlatformNotFoundError(
                        "Count location not found",
                        error_code="location_not_found",
                    )
                if location.usage not in STOCK_QUANT_USAGES:
                    raise PlatformConflictError(
                        "Count is allowed only on quant locations",
                        error_code="location_usage_invalid",
                    )
                quant = await StockQuant.ensure_locked(
                    company_id=company_id,
                    product_id=line.product_id,
                    location_id=line.location_id,
                    lot_id=line.lot_id,
                    owner_entity_id=None,
                    warehouse_id=warehouse_id,
                    quant_id=new_id("qnt"),
                )
                await StockQuant.update_inventory_quantity_counted_at_and_user(
                    quant.quant_id,
                    line.quantity,
                    counted_at=utcnow(),
                    user_id=actor_user_id,
                )
                quant_ids.append(quant.quant_id)
            # Ячейка «посчитана» — cycle-count тик считает просрочку
            # от этой отметки (``last_count_at`` на локации).
            await StockLocation.touch_counted(
                company_id,
                [ln.location_id for ln in context.lines if ln.location_id],
                at=utcnow(),
            )
            return LaneOutcome(result=_QuantIds(ids=quant_ids), events=[])

        async with traced_operation(
            "stock.scan.count_commit",
            operation_category="stock_mutation",
            resource_type="stock_warehouse",
            resource_id=warehouse_id,
            extra_attributes={
                ATTR_TENANT_COMPANY_ID: company_id,
                "stock.warehouse_id": warehouse_id,
                "stock.scan_lines": len(context.lines),
            },
        ):
            run = await run_in_lanes(
                [stock_command_lane(company_id, warehouse_id)],
                company_id=company_id,
                using=STOCK_DB,
                idempotency_key=command_idempotency_key(idempotency_key),
                command_type=command_type,
                actor_user_id=actor_user_id,
                result_type=_QuantIds,
                body=body,
            )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result.ids

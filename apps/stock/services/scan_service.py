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
    StockLot,
    StockMove,
    StockMoveState,
    StockProduct,
    StockQuant,
    StockTransfer,
    UnitOfMeasure,
)
from apps.stock.models.common import STOCK_DB, new_id, stock_command_lane
from apps.stock.models.scan import (
    ScanContext,
    ScanEntityKind,
    ScanError,
    ScanResolution,
    ScanStepResult,
    scan_commit_ready,
    scan_quantity,
    scan_step,
)
from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.move_engine import StockMoveEngine
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
}
"""Тип носителя индекса → тип сущности скан-машины."""


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
        kind = _ENTITY_KIND.get(result.entity_type)
        if kind is None:
            # transfer/resource — распознано, но для скан-потоков бесполезно.
            return ScanResolution(
                entity_kind=ScanEntityKind.UNKNOWN,
                barcode=barcode,
            )
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
                resolution = replace(
                    resolution,
                    product_id=lot.product_id,
                    lot_id=lot.lot_id,
                )
        elif kind == ScanEntityKind.PACKAGING:
            # Упаковка — AUoM: строка stock_uom с product_id; количество
            # базовых единиц = factor / factor(базовой ЕИ товара).
            uom = await UnitOfMeasure.by_id(company_id, result.entity_id)
            product = (
                await StockProduct.by_id(company_id, uom.product_id)
                if uom is not None and uom.product_id is not None
                else None
            )
            base = (
                await UnitOfMeasure.by_id(company_id, product.uom_id)
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

    def step(
        self, *, context: ScanContext, resolution: ScanResolution
    ) -> ScanStepResult:
        """Один скан через чистую машину — контекст возвращается клиенту."""
        return scan_step(context, resolution)

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

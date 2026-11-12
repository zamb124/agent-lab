"""Контракты push-событий склада и их сборка внутри lane-транзакции.

Payload-модели — leaf (только `enums`); события складываются в
``LaneOutcome.events`` и уезжают в durable outbox ``LaneCommit``, публикация —
после commit (`publish_lane_run` / `relay_lane_commits`), доставка
at-least-once с дедупликацией bus по ``event_id``.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from apps.stock.models.enums import (
    StockLocationUsage,
    StockMoveState,
    StockTransferState,
    ValueEntryKind,
)
from core.events.contract import EventDelivery, PlatformEvent, PlatformEventMeta

STOCK_MOVE_DONE = "stock/move/done"
STOCK_TRANSFER_DONE = "stock/transfer/done"
STOCK_QUANT_CHANGED = "stock/quant/changed"
STOCK_VALUATION_CHANGED = "stock/valuation/changed"
STOCK_CONTAINER_MOVED = "stock/container/moved"
STOCK_MOVE_LINE_ASSIGNED = "stock/move_line/assigned"
STOCK_MOVE_LINE_EXCEPTION = "stock/move_line/exception"
STOCK_WAVE_RELEASED = "stock/wave/released"


class StockMoveDonePayload(BaseModel):
    """Факт завершения движения — идентификаторы и операционные поля для фильтров."""

    company_id: str
    move_id: str
    transfer_id: str | None = None
    warehouse_id: str | None = None
    operation_type_id: str | None = None
    operation_code: str | None = None
    product_id: str
    location_id: str
    location_dest_id: str
    location_usage: StockLocationUsage
    location_dest_usage: StockLocationUsage
    state: StockMoveState = StockMoveState.DONE
    quantity: Decimal
    unit_price: Decimal | None = None
    unit_cost: Decimal | None = None
    value: Decimal | None = None
    value_layer_ids: list[str] = Field(default_factory=list)
    returned_move_id: str | None = None
    origin_document_type: str | None = None
    origin_document_id: str | None = None
    done_at: str


class StockTransferDonePayload(BaseModel):
    company_id: str
    transfer_id: str
    warehouse_id: str
    operation_type_id: str
    operation_code: str | None = None
    name: str
    state: StockTransferState = StockTransferState.DONE
    partner_entity_id: str | None = None
    backorder_of_id: str | None = None
    return_of_id: str | None = None
    backorder_transfer_id: str | None = None
    move_ids: list[str] = Field(default_factory=list)
    origin_document_type: str | None = None
    origin_document_id: str | None = None
    done_at: str


class StockQuantChangedPayload(BaseModel):
    """Изменение проекции остатка (done движения / инвентаризация)."""

    company_id: str
    quant_id: str
    product_id: str
    location_id: str
    lot_id: str | None = None
    owner_entity_id: str | None = None
    quantity: Decimal
    reserved_quantity: Decimal
    move_id: str | None = None


class StockContainerMovedPayload(BaseModel):
    """Контейнер-локация перепривязана к новому родителю (поддерево целиком)."""

    company_id: str
    container_id: str
    container_type_id: str | None = None
    from_parent_id: str | None = None
    to_parent_id: str
    warehouse_id: str | None = None
    moved_at: str


class StockMoveLineAssignedPayload(BaseModel):
    """Задание попало к оператору — очередь ТСД перерисовывается."""

    company_id: str
    move_line_id: str
    move_id: str
    transfer_id: str | None = None
    warehouse_id: str | None = None
    wave_id: str | None = None
    assigned_user_id: str | None = None
    resource_id: str | None = None
    claimed: bool = False
    """`claimed=True` — оператор сам взял задание; иначе назначил диспетчер."""


class StockMoveLineExceptionPayload(BaseModel):
    """Исключение по заданию — недостача/бой в ячейке.

    Внешняя реакция (эскалация в задачи платформы, уведомление
    менеджера) подписывается на этот push в flows — сам склад фиксирует
    факт, снимает резерв и ставит пересчёт.
    """

    company_id: str
    move_line_id: str
    move_id: str
    transfer_id: str | None = None
    warehouse_id: str | None = None
    product_id: str
    location_id: str
    shortage: Decimal
    reason: str
    file_ids: list[str] = Field(default_factory=list)
    count_line_id: str | None = None
    reported_by: str | None = None


class StockWaveReleasedPayload(BaseModel):
    """Волна выпущена в работу: её строки стали видны операторам."""

    company_id: str
    wave_id: str
    warehouse_id: str
    name: str
    line_count: int
    released_at: str


class StockValuationChangedPayload(BaseModel):
    """Факт изменения стоимости (revalue/correction — вне done)."""

    company_id: str
    product_id: str
    layer_id: str
    entry_no: int
    entry_kind: ValueEntryKind
    quantity: Decimal
    value: Decimal
    qty_after: Decimal
    value_after: Decimal
    origin_layer_id: str | None = None


def company_event(
    type: str,
    payload: BaseModel,
    *,
    company_id: str,
    actor_user_id: str,
    causation_id: str | None = None,
) -> PlatformEvent:
    """``PlatformEvent`` с доставкой всем сокетам компании — для LaneCommit.events."""
    return PlatformEvent(
        type=type,
        company_id=company_id,
        payload=payload.model_dump(mode="json"),
        meta=PlatformEventMeta(
            source="system",
            actor_user_id=actor_user_id,
            causation_id=causation_id,
        ),
        delivery=EventDelivery(company_id=company_id),
    )


__all__ = [
    "STOCK_CONTAINER_MOVED",
    "STOCK_MOVE_DONE",
    "STOCK_MOVE_LINE_ASSIGNED",
    "STOCK_MOVE_LINE_EXCEPTION",
    "STOCK_QUANT_CHANGED",
    "STOCK_TRANSFER_DONE",
    "STOCK_VALUATION_CHANGED",
    "STOCK_WAVE_RELEASED",
    "StockContainerMovedPayload",
    "StockMoveDonePayload",
    "StockMoveLineAssignedPayload",
    "StockMoveLineExceptionPayload",
    "StockQuantChangedPayload",
    "StockTransferDonePayload",
    "StockValuationChangedPayload",
    "StockWaveReleasedPayload",
    "company_event",
]

"""
События склада на шине `platform:events`.

Публикуются после commit мутации — нотификация для UI и durable-потребителей
(flows-триггеры с `platform_event`-фильтрами), не транспорт записи леджера.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from apps.stock.models.domain import (
    StockLocationUsage,
    StockMoveState,
    StockTransferState,
    ValueEntryKind,
)
from core.events import publish_event_to_company, register_platform_event

STOCK_MOVE_DONE = "stock/move/done"
STOCK_TRANSFER_DONE = "stock/transfer/done"
STOCK_QUANT_CHANGED = "stock/quant/changed"
STOCK_VALUATION_CHANGED = "stock/valuation/changed"


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
    package_id: str | None = None
    owner_entity_id: str | None = None
    quantity: Decimal
    reserved_quantity: Decimal
    move_id: str | None = None


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


register_platform_event(
    STOCK_MOVE_DONE,
    StockMoveDonePayload,
    description="Движение склада завершено (done): quant и слои оценки записаны.",
)
register_platform_event(
    STOCK_TRANSFER_DONE,
    StockTransferDonePayload,
    description="Перевод склада проведён; возможный backorder указан отдельно.",
)
register_platform_event(
    STOCK_QUANT_CHANGED,
    StockQuantChangedPayload,
    description="Проекция остатка изменена (done движения / инвентаризация).",
)
register_platform_event(
    STOCK_VALUATION_CHANGED,
    StockValuationChangedPayload,
    description="Стоимость продукта изменена корректирующим слоем.",
)


async def publish_stock_move_done(
    company_id: str, payload: StockMoveDonePayload
) -> None:
    await publish_event_to_company(
        company_id=company_id,
        type=STOCK_MOVE_DONE,
        payload=payload.model_dump(mode="json"),
    )


async def publish_stock_transfer_done(
    company_id: str, payload: StockTransferDonePayload
) -> None:
    await publish_event_to_company(
        company_id=company_id,
        type=STOCK_TRANSFER_DONE,
        payload=payload.model_dump(mode="json"),
    )


async def publish_stock_quant_changed(
    company_id: str, payload: StockQuantChangedPayload
) -> None:
    await publish_event_to_company(
        company_id=company_id,
        type=STOCK_QUANT_CHANGED,
        payload=payload.model_dump(mode="json"),
    )


async def publish_stock_valuation_changed(
    company_id: str, payload: StockValuationChangedPayload
) -> None:
    await publish_event_to_company(
        company_id=company_id,
        type=STOCK_VALUATION_CHANGED,
        payload=payload.model_dump(mode="json"),
    )


__all__ = [
    "STOCK_MOVE_DONE",
    "STOCK_QUANT_CHANGED",
    "STOCK_TRANSFER_DONE",
    "STOCK_VALUATION_CHANGED",
    "StockMoveDonePayload",
    "StockQuantChangedPayload",
    "StockTransferDonePayload",
    "StockValuationChangedPayload",
    "publish_stock_move_done",
    "publish_stock_quant_changed",
    "publish_stock_transfer_done",
    "publish_stock_valuation_changed",
]

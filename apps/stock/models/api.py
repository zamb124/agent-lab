"""Типизированный контракт команд stock: один payload на `op_*` (WS≡REST).

Payload'ы — `StrictBaseModel` (`extra="forbid"`); ответы — доменные модели
Oxyde напрямую либо композитные `*Detail`/`*Response` из этого файла.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import Field

from apps.stock.models.domain import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockBarcodeEntityType,
    StockLocationUsage,
    StockMove,
    StockMoveLine,
    StockProduct,
    StockProductTemplate,
    StockTracking,
    StockTransfer,
    StockTransferState,
    ValuationMethod,
)
from core.models import StrictBaseModel

ItemT = TypeVar("ItemT")


class StockItemsResponse(StrictBaseModel, Generic[ItemT]):
    """Непагинированный список — WS reply обязан быть JsonObject."""

    items: list[ItemT]


class StockPagePayload(StrictBaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# --- Продукты ---


class StockProductCreatePayload(StrictBaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=1, max_length=128)
    uom_id: str = Field(min_length=1)
    valuation_method: ValuationMethod
    standard_price: Decimal = Field(default=Decimal("0"), ge=0)
    tracking: StockTracking = StockTracking.NONE
    is_storable: bool = True
    category: str = Field(default="", max_length=128)
    barcode: str | None = Field(default=None, max_length=128)


class StockProductUpdatePayload(StrictBaseModel):
    product_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = Field(default=None, min_length=1, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    valuation_method: ValuationMethod | None = None
    standard_price: Decimal | None = Field(default=None, ge=0)
    tracking: StockTracking | None = None


class StockProductIdPayload(StrictBaseModel):
    product_id: str


class StockProductDetail(StrictBaseModel):
    product: StockProduct
    template: StockProductTemplate


# --- Локации ---


class StockLocationCreatePayload(StrictBaseModel):
    warehouse_id: str
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    usage: StockLocationUsage = StockLocationUsage.INTERNAL
    removal_method: str | None = Field(default=None, max_length=32)
    barcode: str | None = Field(default=None, max_length=128)


class StockLocationUpdatePayload(StrictBaseModel):
    location_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    removal_method: str | None = Field(default=None, max_length=32)
    barcode: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class StockLocationIdPayload(StrictBaseModel):
    location_id: str


class StockLocationsListPayload(StrictBaseModel):
    warehouse_id: str | None = None


# --- Склады ---


class StockWarehouseCreatePayload(StrictBaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)


class StockWarehouseUpdatePayload(StrictBaseModel):
    warehouse_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=32)


class StockWarehouseIdPayload(StrictBaseModel):
    warehouse_id: str


# --- Типы операций ---


class StockOperationTypesListPayload(StrictBaseModel):
    warehouse_id: str


class StockOperationTypeUpdatePayload(StrictBaseModel):
    operation_type_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    reservation_policy: ReservationPolicy | None = None
    backorder_policy: BackorderPolicy | None = None
    putaway_mode: ReflexMode | None = None
    putaway_flow_id: str | None = None
    auto_validate: bool | None = None


# --- Transfers / moves ---


class StockMoveSpec(StrictBaseModel):
    """Строка движения в create-transfer."""

    product_id: str
    product_qty: Decimal = Field(gt=0)
    uom_id: str
    unit_price: Decimal | None = Field(default=None, ge=0)
    location_id: str | None = None
    location_dest_id: str | None = None


class StockTransferCreatePayload(StrictBaseModel):
    warehouse_id: str
    operation_type_id: str
    partner_entity_id: str | None = None
    owner_entity_id: str | None = None
    scheduled_at: datetime | None = None
    origin_document_type: str | None = Field(default=None, max_length=64)
    origin_document_id: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=128)
    moves: list[StockMoveSpec] = Field(min_length=1)


class StockTransferIdPayload(StrictBaseModel):
    transfer_id: str


class StockTransfersListPayload(StockPagePayload):
    warehouse_id: str | None = None
    state: StockTransferState | None = None


class StockTransferReturnPayload(StrictBaseModel):
    transfer_id: str
    move_quantities: dict[str, Decimal] | None = None


class StockTransferDetail(StrictBaseModel):
    transfer: StockTransfer
    moves: list[StockMove]
    lines: list[StockMoveLine]


# --- Move lines / решения ---


class StockMoveLineUpdatePayload(StrictBaseModel):
    move_line_id: str
    done_quantity: Decimal | None = Field(default=None, ge=0)
    picked: bool | None = None
    lot_id: str | None = None
    location_dest_id: str | None = None


class StockMoveApplyDecisionPayload(StrictBaseModel):
    move_id: str
    location_id: str


# --- Остатки / инвентаризация ---


class StockQuantsListPayload(StockPagePayload):
    location_id: str | None = None
    product_id: str | None = None


class StockQuantInventorySetPayload(StrictBaseModel):
    quant_id: str
    inventory_quantity: Decimal = Field(ge=0)


class StockQuantInventoryApplyPayload(StrictBaseModel):
    quant_id: str


# --- Оценка ---


class StockValuationLayersPayload(StockPagePayload):
    product_id: str | None = None
    warehouse_id: str | None = None


class StockValuationProductValuePayload(StrictBaseModel):
    product_id: str
    warehouse_id: str | None = None


class StockProductValueResponse(StrictBaseModel):
    product_id: str
    quantity: Decimal
    value: Decimal
    avg_cost: Decimal
    warehouse_id: str | None = None


class StockValuationRevaluePayload(StrictBaseModel):
    product_id: str
    value_delta: Decimal | None = None
    new_price: Decimal | None = Field(default=None, ge=0)
    description: str = Field(default="", max_length=512)


class StockValuationCorrectionPayload(StrictBaseModel):
    origin_layer_id: str
    quantity_delta: Decimal = Decimal("0")
    value_delta: Decimal
    description: str = Field(default="", max_length=512)


# --- Lots / packages ---


class StockLotCreatePayload(StrictBaseModel):
    product_id: str
    name: str = Field(min_length=1, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    expiration_at: datetime | None = None


class StockLotsListPayload(StrictBaseModel):
    product_id: str | None = None


class StockPackageCreatePayload(StrictBaseModel):
    package_type_id: str | None = None
    parent_package_id: str | None = None
    location_id: str | None = None
    barcode: str | None = Field(default=None, max_length=128)


# --- Пульс / barcode / init ---


class StockWarehousePulsePayload(StrictBaseModel):
    warehouse_id: str


class StockPulseTransferRow(StrictBaseModel):
    transfer_id: str
    name: str
    operation_code: str
    state: StockTransferState
    scheduled_at: str | None = None
    age_seconds: float


class StockPulseQuantRow(StrictBaseModel):
    product_id: str
    location_id: str
    quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    avg_cost: Decimal
    value: Decimal
    last_move_at: str | None = None


class StockWarehousePulseResponse(StrictBaseModel):
    warehouse_id: str
    transfers: list[StockPulseTransferRow]
    quants: list[StockPulseQuantRow]


class StockBarcodeResolvePayload(StrictBaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class StockBarcodeResolveResponse(StrictBaseModel):
    entity_type: StockBarcodeEntityType
    entity_id: str


class StockCompanyInitResponse(StrictBaseModel):
    company_id: str
    location_ids: list[str]

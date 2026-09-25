"""Args-модели клиента и tools сервиса stock (WMS).

Поля зеркалят контракты `apps/stock/models/api.py` — сервис валидирует их же.
Для LLM-facing args даты/суммы — строки (ISO/Decimal-string), сервис парсит.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StockEmptyArgs(BaseModel):
    pass


class StockWarehouseIdArgs(BaseModel):
    warehouse_id: str = Field(min_length=1)


class StockTransferIdArgs(BaseModel):
    transfer_id: str = Field(min_length=1)


class StockBarcodeResolveArgs(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class StockQuantsListArgs(BaseModel):
    location_id: str | None = None
    product_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class StockProductsListArgs(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class StockProductCreateArgs(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=1, max_length=128)
    uom_id: str = Field(min_length=1)
    valuation_method: str = Field(
        description="standard | average | fifo | unvalued — обязателен с первого дня"
    )
    standard_price: str = Field(default="0")
    tracking: str = Field(default="none", description="none | lot | serial")
    category: str = Field(default="", max_length=128)
    barcode: str | None = Field(default=None, max_length=128)


class StockLocationsListArgs(BaseModel):
    warehouse_id: str | None = None


class StockMoveSpecArgs(BaseModel):
    product_id: str = Field(min_length=1)
    product_qty: str = Field(description="Количество в ЕИ документа (Decimal-string > 0)")
    uom_id: str = Field(min_length=1)
    unit_price: str | None = Field(
        default=None, description="Входная цена документа (Decimal-string)"
    )
    location_id: str | None = None
    location_dest_id: str | None = None


class StockTransfersListArgs(BaseModel):
    warehouse_id: str | None = None
    transfer_state: str | None = Field(
        default=None,
        description="draft | confirmed | partially_available | assigned | done | cancel",
    )
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class StockTransferCreateArgs(BaseModel):
    warehouse_id: str = Field(min_length=1)
    operation_type_id: str = Field(min_length=1)
    moves: list[StockMoveSpecArgs] = Field(min_length=1)
    partner_entity_id: str | None = None
    owner_entity_id: str | None = None
    scheduled_at: str | None = Field(default=None, description="ISO datetime")
    origin_document_type: str | None = Field(default=None, max_length=64)
    origin_document_id: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=128)


class StockMoveApplyDecisionArgs(BaseModel):
    move_id: str = Field(min_length=1)
    location_id: str = Field(
        min_length=1, description="Локация из candidate_location_ids решения"
    )


class StockValuationProductValueArgs(BaseModel):
    product_id: str = Field(min_length=1)
    warehouse_id: str | None = None


class StockValuationLayersListArgs(BaseModel):
    product_id: str | None = None
    warehouse_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


__all__ = [
    "StockBarcodeResolveArgs",
    "StockEmptyArgs",
    "StockLocationsListArgs",
    "StockMoveApplyDecisionArgs",
    "StockMoveSpecArgs",
    "StockProductCreateArgs",
    "StockProductsListArgs",
    "StockQuantsListArgs",
    "StockTransferCreateArgs",
    "StockTransferIdArgs",
    "StockTransfersListArgs",
    "StockValuationLayersListArgs",
    "StockValuationProductValueArgs",
    "StockWarehouseIdArgs",
]

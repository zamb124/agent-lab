"""Platform Stock (WMS) tools — thin wrappers over StockClient.

Tag: stock. Пишущие инструменты идут только через команды сервиса
(REST-зеркала `stock/<entity>/<verb>_requested`); прямой записи в quant/слои
из tools нет — единственный писатель остатка `StockMoveEngine`, стоимости —
`ValuationService`.
"""

from __future__ import annotations

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.stock_client import StockClient
from core.clients.stock_models import (
    StockBarcodeResolveArgs,
    StockLocationsListArgs,
    StockMoveApplyDecisionArgs,
    StockMoveSpecArgs,
    StockProductCreateArgs,
    StockProductsListArgs,
    StockQuantsListArgs,
    StockTransferCreateArgs,
    StockTransferIdArgs,
    StockTransfersListArgs,
    StockValuationLayersListArgs,
    StockValuationProductValueArgs,
    StockWarehouseIdArgs,
)
from core.state import ExecutionState
from core.types import JsonObject

_TAGS = ["stock"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)


@tool(
    name="stock_warehouse_pulse",
    description=(
        "Warehouse pulse: transfers by state, stock quants with value/avg_cost, "
        "linked work items. Use to answer 'what is happening on warehouse X'."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockWarehouseIdArgs,
    effects=["read"],
)
async def stock_warehouse_pulse(
    *, state: ExecutionState, warehouse_id: str
) -> JsonObject:
    _ = state
    return await StockClient().warehouse_pulse(warehouse_id)


@tool(
    name="stock_quants_list",
    description=(
        "Lists stock quants (on-hand projection). Filter by location_id and/or "
        "product_id. Each item has quantity, reserved_quantity, available."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockQuantsListArgs,
    effects=["read"],
)
async def stock_quants_list(
    *,
    state: ExecutionState,
    location_id: str | None = None,
    product_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> JsonObject:
    _ = state
    return await StockClient().list_quants(
        StockQuantsListArgs(
            location_id=location_id,
            product_id=product_id,
            limit=limit,
            offset=offset,
        )
    )


@tool(
    name="stock_products_list",
    description="Lists stock products (SKU + valuation_method).",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockProductsListArgs,
    effects=["read"],
)
async def stock_products_list(
    *, state: ExecutionState, limit: int = 100, offset: int = 0
) -> JsonObject:
    _ = state
    return await StockClient().list_products(limit=limit, offset=offset)


@tool(
    name="stock_products_create",
    description=(
        "Creates a stock product. valuation_method is "
        "required: standard | average | fifo | unvalued."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockProductCreateArgs,
    effects=["write"],
)
async def stock_products_create(
    *,
    state: ExecutionState,
    name: str,
    sku: str,
    uom_id: str,
    valuation_method: str,
    standard_price: str = "0",
    tracking: str = "none",
    category: str = "",
    barcode: str | None = None,
) -> JsonObject:
    _ = state
    return await StockClient().create_product(
        StockProductCreateArgs(
            name=name,
            sku=sku,
            uom_id=uom_id,
            valuation_method=valuation_method,
            standard_price=standard_price,
            tracking=tracking,
            category=category,
            barcode=barcode,
        )
    )


@tool(
    name="stock_locations_list",
    description=(
        "Lists stock locations (tree, usage: view|internal|supplier|customer|"
        "inventory|production|transit). Filter by warehouse_id."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockLocationsListArgs,
    effects=["read"],
)
async def stock_locations_list(
    *, state: ExecutionState, warehouse_id: str | None = None
) -> JsonObject:
    _ = state
    return await StockClient().list_locations(warehouse_id)


@tool(
    name="stock_transfers_list",
    description=(
        "Lists stock transfers (documents grouping moves). Filter by "
        "warehouse_id and/or state."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockTransfersListArgs,
    effects=["read"],
)
async def stock_transfers_list(
    *,
    state: ExecutionState,
    warehouse_id: str | None = None,
    transfer_state: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> JsonObject:
    _ = state
    return await StockClient().list_transfers(
        StockTransfersListArgs(
            warehouse_id=warehouse_id,
            transfer_state=transfer_state,
            limit=limit,
            offset=offset,
        )
    )


@tool(
    name="stock_transfers_create",
    description=(
        "Creates a stock transfer (draft) with move specs. Receipt = supplier->"
        "internal, shipment = internal->customer, per operation_type defaults."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockTransferCreateArgs,
    effects=["write"],
)
async def stock_transfers_create(
    *,
    state: ExecutionState,
    warehouse_id: str,
    operation_type_id: str,
    moves: list[StockMoveSpecArgs],
    partner_entity_id: str | None = None,
    owner_entity_id: str | None = None,
    scheduled_at: str | None = None,
    origin_document_type: str | None = None,
    origin_document_id: str | None = None,
    barcode: str | None = None,
) -> JsonObject:
    _ = state
    return await StockClient().create_transfer(
        StockTransferCreateArgs(
            warehouse_id=warehouse_id,
            operation_type_id=operation_type_id,
            moves=moves,
            partner_entity_id=partner_entity_id,
            owner_entity_id=owner_entity_id,
            scheduled_at=scheduled_at,
            origin_document_type=origin_document_type,
            origin_document_id=origin_document_id,
            barcode=barcode,
        )
    )


@tool(
    name="stock_transfers_confirm",
    description="Confirms a draft transfer (moves draft->confirmed).",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockTransferIdArgs,
    effects=["write"],
)
async def stock_transfers_confirm(
    *, state: ExecutionState, transfer_id: str
) -> JsonObject:
    _ = state
    return await StockClient().confirm_transfer(transfer_id)


@tool(
    name="stock_transfers_assign",
    description=(
        "Runs reservation/putaway for a confirmed transfer (moves -> assigned/"
        "partially_available)."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockTransferIdArgs,
    effects=["write"],
)
async def stock_transfers_assign(
    *, state: ExecutionState, transfer_id: str
) -> JsonObject:
    _ = state
    return await StockClient().assign_transfer(transfer_id)


@tool(
    name="stock_transfers_validate",
    description=(
        "Validates an assigned transfer: applies quants + valuation layers "
        "atomically (moves -> done, creates backorder on partial)."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockTransferIdArgs,
    effects=["write"],
)
async def stock_transfers_validate(
    *, state: ExecutionState, transfer_id: str
) -> JsonObject:
    _ = state
    return await StockClient().validate_transfer(transfer_id)


@tool(
    name="stock_transfers_cancel",
    description="Cancels a transfer (releases reservations).",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockTransferIdArgs,
    effects=["write"],
)
async def stock_transfers_cancel(
    *, state: ExecutionState, transfer_id: str
) -> JsonObject:
    _ = state
    return await StockClient().cancel_transfer(transfer_id)


@tool(
    name="stock_barcode_resolve",
    description=(
        "Resolves a barcode to its entity (product|packaging|location|"
        "container|lot|transfer|resource) via the stock barcode index and "
        "GS1 semantics."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockBarcodeResolveArgs,
    effects=["read"],
)
async def stock_barcode_resolve(
    *, state: ExecutionState, barcode: str
) -> JsonObject:
    _ = state
    return await StockClient().barcode_resolve(barcode)


@tool(
    name="stock_move_apply_decision",
    description=(
        "Applies a putaway decision: sets move destination to a location from "
        "the suggested candidate_location_ids."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockMoveApplyDecisionArgs,
    effects=["write"],
)
async def stock_move_apply_decision(
    *, state: ExecutionState, move_id: str, location_id: str
) -> JsonObject:
    _ = state
    return await StockClient().move_apply_decision(
        StockMoveApplyDecisionArgs(move_id=move_id, location_id=location_id)
    )


@tool(
    name="stock_valuation_product_value",
    description=(
        "Current stock value for a product: quantity, value, avg_cost "
        "(optionally per warehouse)."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockValuationProductValueArgs,
    effects=["read"],
)
async def stock_valuation_product_value(
    *,
    state: ExecutionState,
    product_id: str,
    warehouse_id: str | None = None,
) -> JsonObject:
    _ = state
    return await StockClient().valuation_product_value(
        StockValuationProductValueArgs(
            product_id=product_id, warehouse_id=warehouse_id
        )
    )


@tool(
    name="stock_valuation_layers_list",
    description=(
        "Lists stock valuation layers (append-only audit journal): entry_no, "
        "entry_kind, quantity, unit_cost, value, qty_after/value_after."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=StockValuationLayersListArgs,
    effects=["read"],
)
async def stock_valuation_layers_list(
    *,
    state: ExecutionState,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> JsonObject:
    _ = state
    return await StockClient().valuation_layers(
        StockValuationLayersListArgs(
            product_id=product_id,
            warehouse_id=warehouse_id,
            limit=limit,
            offset=offset,
        )
    )

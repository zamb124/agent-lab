"""Регистрация WS command-handler'ов stock в `core.websocket`."""

from __future__ import annotations

from apps.stock.di import StockDi
from apps.stock.models.api import (
    StockBarcodeResolvePayload,
    StockLocationCreatePayload,
    StockLocationIdPayload,
    StockLocationsListPayload,
    StockLocationUpdatePayload,
    StockLotCreatePayload,
    StockLotsListPayload,
    StockMoveApplyDecisionPayload,
    StockMoveLineUpdatePayload,
    StockOperationTypesListPayload,
    StockOperationTypeUpdatePayload,
    StockPackageCreatePayload,
    StockPagePayload,
    StockProductCreatePayload,
    StockProductIdPayload,
    StockProductUpdatePayload,
    StockQuantInventoryApplyPayload,
    StockQuantInventorySetPayload,
    StockQuantsListPayload,
    StockTransferCreatePayload,
    StockTransferIdPayload,
    StockTransferReturnPayload,
    StockTransfersListPayload,
    StockValuationCorrectionPayload,
    StockValuationLayersPayload,
    StockValuationProductValuePayload,
    StockValuationRevaluePayload,
    StockWarehouseCreatePayload,
    StockWarehouseIdPayload,
    StockWarehousePulsePayload,
    StockWarehouseUpdatePayload,
)
from apps.stock.realtime.operations import (
    StockCompanyInitPayload,
    op_barcode_resolve,
    op_locations_create,
    op_locations_item,
    op_locations_list,
    op_locations_update,
    op_lots_create,
    op_lots_list,
    op_move_apply_decision,
    op_move_lines_update,
    op_operation_types_list,
    op_operation_types_update,
    op_packages_create,
    op_packages_list,
    op_products_create,
    op_products_item,
    op_products_list,
    op_products_update,
    op_quants_inventory_apply,
    op_quants_inventory_set,
    op_quants_list,
    op_stock_company_init,
    op_transfers_assign,
    op_transfers_cancel,
    op_transfers_confirm,
    op_transfers_create,
    op_transfers_item,
    op_transfers_list,
    op_transfers_return,
    op_transfers_validate,
    op_uoms_list,
    op_valuation_correction,
    op_valuation_layers_list,
    op_valuation_product_value,
    op_valuation_revalue,
    op_warehouse_pulse,
    op_warehouses_create,
    op_warehouses_item,
    op_warehouses_list,
    op_warehouses_update,
)
from core.websocket import EmptyPayload, Operation, RegisteredOperation

STOCK_OPERATIONS: dict[str, RegisteredOperation[StockDi]] = {
    "stock/products/list_requested": Operation(
        payload_model=StockPagePayload, fn=op_products_list
    ),
    "stock/products/item_requested": Operation(
        payload_model=StockProductIdPayload, fn=op_products_item
    ),
    "stock/products/create_requested": Operation(
        payload_model=StockProductCreatePayload, fn=op_products_create
    ),
    "stock/products/update_requested": Operation(
        payload_model=StockProductUpdatePayload, fn=op_products_update
    ),
    "stock/locations/list_requested": Operation(
        payload_model=StockLocationsListPayload, fn=op_locations_list
    ),
    "stock/locations/item_requested": Operation(
        payload_model=StockLocationIdPayload, fn=op_locations_item
    ),
    "stock/locations/create_requested": Operation(
        payload_model=StockLocationCreatePayload, fn=op_locations_create
    ),
    "stock/locations/update_requested": Operation(
        payload_model=StockLocationUpdatePayload, fn=op_locations_update
    ),
    "stock/warehouses/list_requested": Operation(
        payload_model=StockPagePayload, fn=op_warehouses_list
    ),
    "stock/warehouses/item_requested": Operation(
        payload_model=StockWarehouseIdPayload, fn=op_warehouses_item
    ),
    "stock/warehouses/create_requested": Operation(
        payload_model=StockWarehouseCreatePayload, fn=op_warehouses_create
    ),
    "stock/warehouses/update_requested": Operation(
        payload_model=StockWarehouseUpdatePayload, fn=op_warehouses_update
    ),
    "stock/operation_types/list_requested": Operation(
        payload_model=StockOperationTypesListPayload, fn=op_operation_types_list
    ),
    "stock/operation_types/update_requested": Operation(
        payload_model=StockOperationTypeUpdatePayload, fn=op_operation_types_update
    ),
    "stock/transfers/list_requested": Operation(
        payload_model=StockTransfersListPayload, fn=op_transfers_list
    ),
    "stock/transfers/item_requested": Operation(
        payload_model=StockTransferIdPayload, fn=op_transfers_item
    ),
    "stock/transfers/create_requested": Operation(
        payload_model=StockTransferCreatePayload, fn=op_transfers_create
    ),
    "stock/transfers/confirm_requested": Operation(
        payload_model=StockTransferIdPayload, fn=op_transfers_confirm
    ),
    "stock/transfers/assign_requested": Operation(
        payload_model=StockTransferIdPayload, fn=op_transfers_assign
    ),
    "stock/transfers/validate_requested": Operation(
        payload_model=StockTransferIdPayload, fn=op_transfers_validate
    ),
    "stock/transfers/cancel_requested": Operation(
        payload_model=StockTransferIdPayload, fn=op_transfers_cancel
    ),
    "stock/transfers/return_requested": Operation(
        payload_model=StockTransferReturnPayload, fn=op_transfers_return
    ),
    "stock/move_lines/update_requested": Operation(
        payload_model=StockMoveLineUpdatePayload, fn=op_move_lines_update
    ),
    "stock/move/apply_decision_requested": Operation(
        payload_model=StockMoveApplyDecisionPayload, fn=op_move_apply_decision
    ),
    "stock/quants/list_requested": Operation(
        payload_model=StockQuantsListPayload, fn=op_quants_list
    ),
    "stock/quants/inventory_set_requested": Operation(
        payload_model=StockQuantInventorySetPayload, fn=op_quants_inventory_set
    ),
    "stock/quants/inventory_apply_requested": Operation(
        payload_model=StockQuantInventoryApplyPayload, fn=op_quants_inventory_apply
    ),
    "stock/valuation/layers_list_requested": Operation(
        payload_model=StockValuationLayersPayload, fn=op_valuation_layers_list
    ),
    "stock/valuation/product_value_requested": Operation(
        payload_model=StockValuationProductValuePayload, fn=op_valuation_product_value
    ),
    "stock/valuation/revalue_requested": Operation(
        payload_model=StockValuationRevaluePayload, fn=op_valuation_revalue
    ),
    "stock/valuation/correction_requested": Operation(
        payload_model=StockValuationCorrectionPayload, fn=op_valuation_correction
    ),
    "stock/lots/list_requested": Operation(
        payload_model=StockLotsListPayload, fn=op_lots_list
    ),
    "stock/lots/create_requested": Operation(
        payload_model=StockLotCreatePayload, fn=op_lots_create
    ),
    "stock/packages/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_packages_list
    ),
    "stock/packages/create_requested": Operation(
        payload_model=StockPackageCreatePayload, fn=op_packages_create
    ),
    "stock/uoms/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_uoms_list
    ),
    "stock/warehouse/pulse_requested": Operation(
        payload_model=StockWarehousePulsePayload, fn=op_warehouse_pulse
    ),
    "stock/barcode/resolve_requested": Operation(
        payload_model=StockBarcodeResolvePayload, fn=op_barcode_resolve
    ),
    "stock/company/init_requested": Operation(
        payload_model=StockCompanyInitPayload, fn=op_stock_company_init
    ),
}

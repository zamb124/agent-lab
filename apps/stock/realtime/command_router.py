"""Регистрация WS command-handler'ов stock в `core.websocket`."""

from __future__ import annotations

from apps.stock.di import StockDi
from apps.stock.models.api import (
    StockBarcodeResolvePayload,
    StockContainerCreatePayload,
    StockContainerIdPayload,
    StockContainerMovePayload,
    StockContainersListPayload,
    StockContainerTypeCreatePayload,
    StockContainerTypesListPayload,
    StockContainerTypeUpdatePayload,
    StockLocationCreatePayload,
    StockLocationIdPayload,
    StockLocationsCountDuePayload,
    StockLocationsListPayload,
    StockLocationUpdatePayload,
    StockLotCreatePayload,
    StockLotsListPayload,
    StockMoveApplyDecisionPayload,
    StockMoveLineExceptionPayload,
    StockMoveLineNextPayload,
    StockMoveLinesAssignPayload,
    StockMoveLinesClaimPayload,
    StockMoveLinesQueuePayload,
    StockMoveLinesReleasePayload,
    StockMoveLineUpdatePayload,
    StockMovesListPayload,
    StockOperationTypesListPayload,
    StockOperationTypeUpdatePayload,
    StockPackagingCreatePayload,
    StockPackagingIdPayload,
    StockPackagingsListPayload,
    StockPagePayload,
    StockProductCreatePayload,
    StockProductIdPayload,
    StockProductUpdatePayload,
    StockPutawayRuleCreatePayload,
    StockPutawayRuleDeletePayload,
    StockPutawayRulesListPayload,
    StockPutawayRuleUpdatePayload,
    StockQuantInventoryApplyPayload,
    StockQuantInventorySetPayload,
    StockQuantsListPayload,
    StockReorderRuleCreatePayload,
    StockReorderRulesListPayload,
    StockReorderRuleUpdatePayload,
    StockResourceCreatePayload,
    StockResourceLoginPayload,
    StockResourceLogoutPayload,
    StockResourcesListPayload,
    StockResourceTypeCreatePayload,
    StockResourceTypesListPayload,
    StockResourceTypeUpdatePayload,
    StockResourceUpdatePayload,
    StockRouteCreatePayload,
    StockRouteIdPayload,
    StockRoutesListPayload,
    StockScanCommitPayload,
    StockScanCountCommitPayload,
    StockScanQuantityPayload,
    StockScanStepPayload,
    StockStorageTypeCreatePayload,
    StockStorageTypesListPayload,
    StockStorageTypeUpdatePayload,
    StockTransferCreatePayload,
    StockTransferIdPayload,
    StockTransferReturnPayload,
    StockTransfersListPayload,
    StockTransferValidatePayload,
    StockValuationCorrectionPayload,
    StockValuationLayersPayload,
    StockValuationProductValuePayload,
    StockValuationReportPayload,
    StockValuationRevaluePayload,
    StockWarehouseCreatePayload,
    StockWarehouseIdPayload,
    StockWarehousePulsePayload,
    StockWarehouseUpdatePayload,
    StockWaveCreatePayload,
    StockWaveIdPayload,
    StockWavesListPayload,
)
from apps.stock.realtime.operations import (
    StockCompanyInitPayload,
    op_barcode_resolve,
    op_container_types_create,
    op_container_types_list,
    op_container_types_update,
    op_containers_create,
    op_containers_item,
    op_containers_list,
    op_containers_move,
    op_locations_count_due,
    op_locations_create,
    op_locations_item,
    op_locations_list,
    op_locations_update,
    op_lots_create,
    op_lots_list,
    op_move_apply_decision,
    op_move_lines_assign,
    op_move_lines_claim,
    op_move_lines_next,
    op_move_lines_queue,
    op_move_lines_release,
    op_move_lines_report_exception,
    op_move_lines_update,
    op_moves_list,
    op_operation_types_list,
    op_operation_types_update,
    op_packagings_create,
    op_packagings_delete,
    op_packagings_list,
    op_products_create,
    op_products_item,
    op_products_list,
    op_products_update,
    op_putaway_rules_create,
    op_putaway_rules_delete,
    op_putaway_rules_list,
    op_putaway_rules_update,
    op_quants_inventory_apply,
    op_quants_inventory_set,
    op_quants_list,
    op_reorder_rules_create,
    op_reorder_rules_list,
    op_reorder_rules_update,
    op_resource_types_create,
    op_resource_types_list,
    op_resource_types_update,
    op_resources_create,
    op_resources_list,
    op_resources_login,
    op_resources_logout,
    op_resources_update,
    op_routes_create,
    op_routes_get,
    op_routes_list,
    op_scan_commit,
    op_scan_count_commit,
    op_scan_quantity,
    op_scan_step,
    op_stock_company_init,
    op_storage_types_create,
    op_storage_types_list,
    op_storage_types_update,
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
    op_valuation_report,
    op_valuation_revalue,
    op_warehouse_pulse,
    op_warehouses_create,
    op_warehouses_item,
    op_warehouses_list,
    op_warehouses_update,
    op_waves_create,
    op_waves_list,
    op_waves_release,
)
from core.catalog import operations as catalog_ops
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
    "stock/catalog_products/list_requested": Operation(
        payload_model=catalog_ops.CatalogProductsListPayload,
        fn=catalog_ops.op_products_list,
    ),
    "stock/catalog_products/item_requested": Operation(
        payload_model=catalog_ops.CatalogProductIdPayload,
        fn=catalog_ops.op_products_item,
    ),
    "stock/catalog_products/suggest_requested": Operation(
        payload_model=catalog_ops.CatalogProductsSuggestPayload,
        fn=catalog_ops.op_products_suggest,
    ),
    "stock/catalog_products/create_requested": Operation(
        payload_model=catalog_ops.CatalogProductCreatePayload,
        fn=catalog_ops.op_products_create,
    ),
    "stock/catalog_products/update_requested": Operation(
        payload_model=catalog_ops.CatalogProductUpdatePayload,
        fn=catalog_ops.op_products_update,
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
    "stock/locations/count_due_requested": Operation(
        payload_model=StockLocationsCountDuePayload, fn=op_locations_count_due
    ),
    "stock/moves/list_requested": Operation(
        payload_model=StockMovesListPayload, fn=op_moves_list
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
        payload_model=StockTransferValidatePayload, fn=op_transfers_validate
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
    "stock/move_lines/queue_requested": Operation(
        payload_model=StockMoveLinesQueuePayload, fn=op_move_lines_queue
    ),
    "stock/move_lines/next_requested": Operation(
        payload_model=StockMoveLineNextPayload, fn=op_move_lines_next
    ),
    "stock/move_lines/claim_requested": Operation(
        payload_model=StockMoveLinesClaimPayload, fn=op_move_lines_claim
    ),
    "stock/move_lines/assign_requested": Operation(
        payload_model=StockMoveLinesAssignPayload, fn=op_move_lines_assign
    ),
    "stock/move_lines/release_requested": Operation(
        payload_model=StockMoveLinesReleasePayload, fn=op_move_lines_release
    ),
    "stock/move_lines/report_exception_requested": Operation(
        payload_model=StockMoveLineExceptionPayload,
        fn=op_move_lines_report_exception,
    ),
    "stock/waves/list_requested": Operation(
        payload_model=StockWavesListPayload, fn=op_waves_list
    ),
    "stock/waves/create_requested": Operation(
        payload_model=StockWaveCreatePayload, fn=op_waves_create
    ),
    "stock/waves/release_requested": Operation(
        payload_model=StockWaveIdPayload, fn=op_waves_release
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
    "stock/valuation/report_requested": Operation(
        payload_model=StockValuationReportPayload, fn=op_valuation_report
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
    "stock/storage_types/list_requested": Operation(
        payload_model=StockStorageTypesListPayload, fn=op_storage_types_list
    ),
    "stock/storage_types/create_requested": Operation(
        payload_model=StockStorageTypeCreatePayload, fn=op_storage_types_create
    ),
    "stock/storage_types/update_requested": Operation(
        payload_model=StockStorageTypeUpdatePayload, fn=op_storage_types_update
    ),
    "stock/reorder_rules/list_requested": Operation(
        payload_model=StockReorderRulesListPayload, fn=op_reorder_rules_list
    ),
    "stock/reorder_rules/create_requested": Operation(
        payload_model=StockReorderRuleCreatePayload, fn=op_reorder_rules_create
    ),
    "stock/reorder_rules/update_requested": Operation(
        payload_model=StockReorderRuleUpdatePayload, fn=op_reorder_rules_update
    ),
    "stock/putaway_rules/list_requested": Operation(
        payload_model=StockPutawayRulesListPayload, fn=op_putaway_rules_list
    ),
    "stock/putaway_rules/create_requested": Operation(
        payload_model=StockPutawayRuleCreatePayload, fn=op_putaway_rules_create
    ),
    "stock/putaway_rules/update_requested": Operation(
        payload_model=StockPutawayRuleUpdatePayload, fn=op_putaway_rules_update
    ),
    "stock/putaway_rules/delete_requested": Operation(
        payload_model=StockPutawayRuleDeletePayload, fn=op_putaway_rules_delete
    ),
    "stock/routes/list_requested": Operation(
        payload_model=StockRoutesListPayload, fn=op_routes_list
    ),
    "stock/routes/get_requested": Operation(
        payload_model=StockRouteIdPayload, fn=op_routes_get
    ),
    "stock/routes/create_requested": Operation(
        payload_model=StockRouteCreatePayload, fn=op_routes_create
    ),
    "stock/container_types/list_requested": Operation(
        payload_model=StockContainerTypesListPayload, fn=op_container_types_list
    ),
    "stock/container_types/create_requested": Operation(
        payload_model=StockContainerTypeCreatePayload, fn=op_container_types_create
    ),
    "stock/container_types/update_requested": Operation(
        payload_model=StockContainerTypeUpdatePayload,
        fn=op_container_types_update,
    ),
    "stock/resource_types/list_requested": Operation(
        payload_model=StockResourceTypesListPayload, fn=op_resource_types_list
    ),
    "stock/resource_types/create_requested": Operation(
        payload_model=StockResourceTypeCreatePayload, fn=op_resource_types_create
    ),
    "stock/resource_types/update_requested": Operation(
        payload_model=StockResourceTypeUpdatePayload,
        fn=op_resource_types_update,
    ),
    "stock/resources/list_requested": Operation(
        payload_model=StockResourcesListPayload, fn=op_resources_list
    ),
    "stock/resources/create_requested": Operation(
        payload_model=StockResourceCreatePayload, fn=op_resources_create
    ),
    "stock/resources/update_requested": Operation(
        payload_model=StockResourceUpdatePayload, fn=op_resources_update
    ),
    "stock/resources/login_requested": Operation(
        payload_model=StockResourceLoginPayload, fn=op_resources_login
    ),
    "stock/resources/logout_requested": Operation(
        payload_model=StockResourceLogoutPayload, fn=op_resources_logout
    ),
    "stock/containers/list_requested": Operation(
        payload_model=StockContainersListPayload, fn=op_containers_list
    ),
    "stock/containers/create_requested": Operation(
        payload_model=StockContainerCreatePayload, fn=op_containers_create
    ),
    "stock/containers/item_requested": Operation(
        payload_model=StockContainerIdPayload, fn=op_containers_item
    ),
    "stock/containers/move_requested": Operation(
        payload_model=StockContainerMovePayload, fn=op_containers_move
    ),
    "stock/packagings/list_requested": Operation(
        payload_model=StockPackagingsListPayload, fn=op_packagings_list
    ),
    "stock/packagings/create_requested": Operation(
        payload_model=StockPackagingCreatePayload, fn=op_packagings_create
    ),
    "stock/packagings/delete_requested": Operation(
        payload_model=StockPackagingIdPayload, fn=op_packagings_delete
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
    "stock/scan/step_requested": Operation(
        payload_model=StockScanStepPayload, fn=op_scan_step
    ),
    "stock/scan/quantity_requested": Operation(
        payload_model=StockScanQuantityPayload, fn=op_scan_quantity
    ),
    "stock/scan/commit_requested": Operation(
        payload_model=StockScanCommitPayload, fn=op_scan_commit
    ),
    "stock/scan/count_commit_requested": Operation(
        payload_model=StockScanCountCommitPayload, fn=op_scan_count_commit
    ),
    "stock/company/init_requested": Operation(
        payload_model=StockCompanyInitPayload, fn=op_stock_company_init
    ),
}

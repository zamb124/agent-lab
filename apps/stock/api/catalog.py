"""REST-зеркало справочников stock: products/locations/warehouses/operation-types,
quants/valuation/lots/topology(storage/containers/resources/packagings)/uoms/pulse/barcode."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from apps.stock.di import Di
from apps.stock.models import (
    StockContainerType,
    StockLocation,
    StockLot,
    StockMove,
    StockMoveState,
    StockOperationType,
    StockPutawayRule,
    StockQuant,
    StockReorderRule,
    StockResource,
    StockResourceType,
    StockRoute,
    StockStorageType,
    StockTransfer,
    StockValueLayer,
    StockWarehouse,
    ValueEntryKind,
)
from apps.stock.models.api import (
    StockBarcodeResolvePayload,
    StockBarcodeResolveResponse,
    StockContainerContentsResponse,
    StockContainerCreatePayload,
    StockContainerIdPayload,
    StockContainerMovePayload,
    StockContainersListPayload,
    StockContainerTypeCreatePayload,
    StockContainerTypesListPayload,
    StockContainerTypeUpdatePayload,
    StockItemsResponse,
    StockLocationCreatePayload,
    StockLocationIdPayload,
    StockLocationsCountDuePayload,
    StockLocationsListPayload,
    StockLocationUpdatePayload,
    StockLotCreatePayload,
    StockLotsListPayload,
    StockMovesListPayload,
    StockOperationTypesListPayload,
    StockOperationTypeUpdatePayload,
    StockOperatorPulsePayload,
    StockOperatorPulseResponse,
    StockPackagingCreatePayload,
    StockPackagingIdPayload,
    StockPackagingsListPayload,
    StockPagePayload,
    StockProductCreatePayload,
    StockProductIdPayload,
    StockProductUpdatePayload,
    StockProductValueResponse,
    StockProductView,
    StockPutawayRuleCreatePayload,
    StockPutawayRuleDeletePayload,
    StockPutawayRulesListPayload,
    StockPutawayRuleUpdatePayload,
    StockPutawaySuggestPayload,
    StockPutawaySuggestResponse,
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
    StockScanAdhocCommitPayload,
    StockScanCommitPayload,
    StockScanCountCommitPayload,
    StockScanCountCommitResponse,
    StockScanOpenPayload,
    StockScanOpenResponse,
    StockScanQuantityPayload,
    StockScanStepPayload,
    StockScanStepResponse,
    StockStorageTypeCreatePayload,
    StockStorageTypesListPayload,
    StockStorageTypeUpdatePayload,
    StockValuationCorrectionPayload,
    StockValuationLayersPage,
    StockValuationLayersPayload,
    StockValuationProductValuePayload,
    StockValuationReportPayload,
    StockValuationReportResponse,
    StockValuationRevaluePayload,
    StockWarehouseCreatePayload,
    StockWarehouseIdPayload,
    StockWarehousePulsePayload,
    StockWarehousePulseResponse,
    StockWarehouseUpdatePayload,
)
from apps.stock.models.resource import StockResourceLogoutResult
from apps.stock.realtime.operations import (
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
    op_moves_list,
    op_operation_types_list,
    op_operation_types_update,
    op_operator_pulse,
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
    op_putaway_suggest,
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
    op_scan_adhoc_commit,
    op_scan_commit,
    op_scan_count_commit,
    op_scan_open,
    op_scan_quantity,
    op_scan_step,
    op_storage_types_create,
    op_storage_types_list,
    op_storage_types_update,
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
)
from core.catalog import operations as catalog_ops
from core.catalog.contracts import CatalogPackagingView
from core.catalog.models import CatalogProduct, CatalogUom
from core.context import require_context
from core.pagination import CursorPage, ListResponse, OffsetPage
from core.websocket import EmptyPayload, raise_invalid

router = APIRouter(tags=["stock-catalog"])


def _user():
    return require_context().user


# --- Products ---


@router.get("/products", response_model=OffsetPage[StockProductView])
async def list_products(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockProductView]:
    return await op_products_list(
        StockPagePayload(limit=limit, offset=offset), user=_user(), di=di
    )


@router.post("/products", response_model=StockProductView)
async def create_product(
    di: Di, body: StockProductCreatePayload
) -> StockProductView:
    return await op_products_create(body, user=_user(), di=di)


@router.get("/products/{product_id}", response_model=StockProductView)
async def get_product(di: Di, product_id: str) -> StockProductView:
    return await op_products_item(
        StockProductIdPayload(product_id=product_id), user=_user(), di=di
    )


@router.patch("/products/{product_id}", response_model=StockProductView)
async def update_product(
    di: Di, product_id: str, body: StockProductUpdatePayload
) -> StockProductView:
    if body.product_id != product_id:
        raise_invalid(ValueError("product_id mismatch"), error_code="path_id_mismatch")
    return await op_products_update(body, user=_user(), di=di)


# --- Мастер-карточка каталога (общая база товаров компании) ---


@router.get(
    "/catalog-products/suggest", response_model=ListResponse[CatalogProduct]
)
async def suggest_catalog_products(
    di: Di,
    name: Annotated[str | None, Query(max_length=300)] = None,
    sku: Annotated[str | None, Query(max_length=128)] = None,
    barcode: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> ListResponse[CatalogProduct]:
    return await catalog_ops.op_products_suggest(
        catalog_ops.CatalogProductsSuggestPayload(
            name=name, sku=sku, barcode=barcode, limit=limit
        ),
        user=_user(),
        di=di,
    )


@router.patch("/catalog-products/{product_id}", response_model=CatalogProduct)
async def update_catalog_product(
    di: Di, product_id: str, body: catalog_ops.CatalogProductUpdatePayload
) -> CatalogProduct:
    if body.product_id != product_id:
        raise_invalid(ValueError("product_id mismatch"), error_code="path_id_mismatch")
    return await catalog_ops.op_products_update(body, user=_user(), di=di)


# --- Locations ---


@router.get("/locations", response_model=StockItemsResponse[StockLocation])
async def list_locations(
    di: Di, warehouse_id: str | None = None, include_virtual: bool = False
) -> StockItemsResponse[StockLocation]:
    return await op_locations_list(
        StockLocationsListPayload(
            warehouse_id=warehouse_id, include_virtual=include_virtual
        ),
        user=_user(),
        di=di,
    )


@router.post("/locations", response_model=StockLocation)
async def create_location(di: Di, body: StockLocationCreatePayload) -> StockLocation:
    return await op_locations_create(body, user=_user(), di=di)


@router.get(
    "/locations/count-due",
    response_model=StockItemsResponse[StockLocation],
)
async def list_count_due_locations(
    di: Di,
    warehouse_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> StockItemsResponse[StockLocation]:
    return await op_locations_count_due(
        StockLocationsCountDuePayload(warehouse_id=warehouse_id, limit=limit),
        user=_user(),
        di=di,
    )


@router.get("/moves", response_model=CursorPage[StockMove])
async def list_moves(
    di: Di,
    warehouse_id: str | None = None,
    location_id: str | None = None,
    subtree: bool = False,
    product_id: str | None = None,
    state: StockMoveState | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: str | None = None,
) -> CursorPage[StockMove]:
    return await op_moves_list(
        StockMovesListPayload(
            warehouse_id=warehouse_id,
            location_id=location_id,
            subtree=subtree,
            product_id=product_id,
            state=state,
            limit=limit,
            cursor=cursor,
        ),
        user=_user(),
        di=di,
    )


@router.get("/locations/{location_id}", response_model=StockLocation)
async def get_location(di: Di, location_id: str) -> StockLocation:
    return await op_locations_item(
        StockLocationIdPayload(location_id=location_id), user=_user(), di=di
    )


@router.patch("/locations/{location_id}", response_model=StockLocation)
async def update_location(
    di: Di, location_id: str, body: StockLocationUpdatePayload
) -> StockLocation:
    if body.location_id != location_id:
        raise_invalid(ValueError("location_id mismatch"), error_code="path_id_mismatch")
    return await op_locations_update(body, user=_user(), di=di)


# --- Warehouses ---


@router.get("/warehouses", response_model=OffsetPage[StockWarehouse])
async def list_warehouses(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockWarehouse]:
    return await op_warehouses_list(
        StockPagePayload(limit=limit, offset=offset), user=_user(), di=di
    )


@router.post("/warehouses", response_model=StockWarehouse)
async def create_warehouse(
    di: Di, body: StockWarehouseCreatePayload
) -> StockWarehouse:
    return await op_warehouses_create(body, user=_user(), di=di)


@router.get("/warehouses/{warehouse_id}", response_model=StockWarehouse)
async def get_warehouse(di: Di, warehouse_id: str) -> StockWarehouse:
    return await op_warehouses_item(
        StockWarehouseIdPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.patch("/warehouses/{warehouse_id}", response_model=StockWarehouse)
async def update_warehouse(
    di: Di, warehouse_id: str, body: StockWarehouseUpdatePayload
) -> StockWarehouse:
    if body.warehouse_id != warehouse_id:
        raise_invalid(ValueError("warehouse_id mismatch"), error_code="path_id_mismatch")
    return await op_warehouses_update(body, user=_user(), di=di)


@router.get("/warehouses/{warehouse_id}/pulse", response_model=StockWarehousePulseResponse)
async def warehouse_pulse(di: Di, warehouse_id: str) -> StockWarehousePulseResponse:
    return await op_warehouse_pulse(
        StockWarehousePulsePayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.get(
    "/warehouses/{warehouse_id}/operator-pulse",
    response_model=StockOperatorPulseResponse,
)
async def operator_pulse(
    di: Di,
    warehouse_id: str,
    window_hours: Annotated[int, Query(ge=1, le=24)] = 8,
) -> StockOperatorPulseResponse:
    return await op_operator_pulse(
        StockOperatorPulsePayload(
            warehouse_id=warehouse_id, window_hours=window_hours
        ),
        user=_user(),
        di=di,
    )


# --- Operation types ---


@router.get("/operation-types", response_model=StockItemsResponse[StockOperationType])
async def list_operation_types(
    di: Di, warehouse_id: str
) -> StockItemsResponse[StockOperationType]:
    return await op_operation_types_list(
        StockOperationTypesListPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.patch("/operation-types/{operation_type_id}", response_model=StockOperationType)
async def update_operation_type(
    di: Di, operation_type_id: str, body: StockOperationTypeUpdatePayload
) -> StockOperationType:
    if body.operation_type_id != operation_type_id:
        raise_invalid(ValueError("operation_type_id mismatch"), error_code="path_id_mismatch")
    return await op_operation_types_update(body, user=_user(), di=di)


# --- Quants / inventory ---


@router.get("/quants", response_model=OffsetPage[StockQuant])
async def list_quants(
    di: Di,
    location_id: str | None = None,
    product_id: str | None = None,
    owner_entity_id: str | None = None,
    warehouse_id: str | None = None,
    subtree_location_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockQuant]:
    return await op_quants_list(
        StockQuantsListPayload(
            location_id=location_id,
            product_id=product_id,
            owner_entity_id=owner_entity_id,
            warehouse_id=warehouse_id,
            subtree_location_id=subtree_location_id,
            limit=limit,
            offset=offset,
        ),
        user=_user(),
        di=di,
    )


@router.post("/quants/inventory-set", response_model=StockQuant)
async def inventory_set(
    di: Di, body: StockQuantInventorySetPayload
) -> StockQuant:
    return await op_quants_inventory_set(body, user=_user(), di=di)


@router.post("/quants/inventory-apply", response_model=StockMove)
async def inventory_apply(
    di: Di, body: StockQuantInventoryApplyPayload
) -> StockMove:
    return await op_quants_inventory_apply(body, user=_user(), di=di)


# --- Valuation ---


@router.get("/valuation/layers", response_model=StockValuationLayersPage)
async def list_valuation_layers(
    di: Di,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    transfer_id: str | None = None,
    entry_kinds: list[ValueEntryKind] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    open_only: bool = False,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StockValuationLayersPage:
    return await op_valuation_layers_list(
        StockValuationLayersPayload(
            product_id=product_id,
            warehouse_id=warehouse_id,
            transfer_id=transfer_id,
            entry_kinds=entry_kinds,
            date_from=date_from,
            date_to=date_to,
            open_only=open_only,
            search=search,
            limit=limit,
            offset=offset,
        ),
        user=_user(),
        di=di,
    )


@router.get("/valuation/report", response_model=StockValuationReportResponse)
async def valuation_report(
    di: Di,
    warehouse_id: str | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StockValuationReportResponse:
    return await op_valuation_report(
        StockValuationReportPayload(
            warehouse_id=warehouse_id,
            search=search,
            limit=limit,
            offset=offset,
        ),
        user=_user(),
        di=di,
    )


@router.get("/valuation/product-value", response_model=StockProductValueResponse)
async def product_value(
    di: Di, product_id: str, warehouse_id: str | None = None
) -> StockProductValueResponse:
    return await op_valuation_product_value(
        StockValuationProductValuePayload(
            product_id=product_id, warehouse_id=warehouse_id
        ),
        user=_user(),
        di=di,
    )


@router.post("/valuation/revalue", response_model=StockValueLayer)
async def revalue(di: Di, body: StockValuationRevaluePayload) -> StockValueLayer:
    return await op_valuation_revalue(body, user=_user(), di=di)


@router.post("/valuation/correction", response_model=StockValueLayer)
async def correction(
    di: Di, body: StockValuationCorrectionPayload
) -> StockValueLayer:
    return await op_valuation_correction(body, user=_user(), di=di)


# --- Lots / topology / uoms / barcode ---


@router.get("/lots", response_model=StockItemsResponse[StockLot])
async def list_lots(
    di: Di, product_id: str | None = None
) -> StockItemsResponse[StockLot]:
    return await op_lots_list(
        StockLotsListPayload(product_id=product_id), user=_user(), di=di
    )


@router.post("/lots", response_model=StockLot)
async def create_lot(di: Di, body: StockLotCreatePayload) -> StockLot:
    return await op_lots_create(body, user=_user(), di=di)


# --- Топология ---


@router.get("/storage-types", response_model=StockItemsResponse[StockStorageType])
async def list_storage_types(
    di: Di, warehouse_id: str
) -> StockItemsResponse[StockStorageType]:
    return await op_storage_types_list(
        StockStorageTypesListPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.post("/storage-types", response_model=StockStorageType)
async def create_storage_type(
    di: Di, body: StockStorageTypeCreatePayload
) -> StockStorageType:
    return await op_storage_types_create(body, user=_user(), di=di)


@router.patch(
    "/storage-types/{storage_type_id}", response_model=StockStorageType
)
async def update_storage_type(
    di: Di, storage_type_id: str, body: StockStorageTypeUpdatePayload
) -> StockStorageType:
    if body.storage_type_id != storage_type_id:
        raise_invalid(
            ValueError("storage_type_id mismatch"), error_code="path_id_mismatch"
        )
    return await op_storage_types_update(body, user=_user(), di=di)


# --- Маршруты цепочек ---


@router.post(
    "/reorder-rules/list", response_model=StockItemsResponse[StockReorderRule]
)
async def reorder_rules_list(
    di: Di, body: StockReorderRulesListPayload
) -> StockItemsResponse[StockReorderRule]:
    return await op_reorder_rules_list(body, user=_user(), di=di)


@router.post("/reorder-rules", response_model=StockReorderRule)
async def reorder_rules_create(
    di: Di, body: StockReorderRuleCreatePayload
) -> StockReorderRule:
    return await op_reorder_rules_create(body, user=_user(), di=di)


@router.patch(
    "/reorder-rules/{rule_id}/active", response_model=StockReorderRule
)
async def reorder_rules_update(
    di: Di, rule_id: str, body: StockReorderRuleUpdatePayload
) -> StockReorderRule:
    if body.rule_id != rule_id:
        raise_invalid(ValueError("rule_id mismatch"), error_code="path_id_mismatch")
    return await op_reorder_rules_update(body, user=_user(), di=di)


@router.post(
    "/putaway-rules/list", response_model=StockItemsResponse[StockPutawayRule]
)
async def putaway_rules_list(
    di: Di, body: StockPutawayRulesListPayload
) -> StockItemsResponse[StockPutawayRule]:
    return await op_putaway_rules_list(body, user=_user(), di=di)


@router.post("/putaway-rules", response_model=StockPutawayRule)
async def putaway_rules_create(
    di: Di, body: StockPutawayRuleCreatePayload
) -> StockPutawayRule:
    return await op_putaway_rules_create(body, user=_user(), di=di)


@router.patch(
    "/putaway-rules/{rule_id}", response_model=StockPutawayRule
)
async def putaway_rules_update(
    di: Di, rule_id: str, body: StockPutawayRuleUpdatePayload
) -> StockPutawayRule:
    if body.rule_id != rule_id:
        raise_invalid(ValueError("rule_id mismatch"), error_code="path_id_mismatch")
    return await op_putaway_rules_update(body, user=_user(), di=di)


@router.post(
    "/putaway-rules/{rule_id}/delete", response_model=StockPutawayRule
)
async def putaway_rules_delete(
    di: Di, rule_id: str, body: StockPutawayRuleDeletePayload
) -> StockPutawayRule:
    if body.rule_id != rule_id:
        raise_invalid(ValueError("rule_id mismatch"), error_code="path_id_mismatch")
    return await op_putaway_rules_delete(body, user=_user(), di=di)


@router.post("/putaway/suggest", response_model=StockPutawaySuggestResponse)
async def putaway_suggest(
    di: Di, body: StockPutawaySuggestPayload
) -> StockPutawaySuggestResponse:
    return await op_putaway_suggest(body, user=_user(), di=di)


@router.post("/routes/list", response_model=StockItemsResponse[StockRoute])
async def routes_list(
    di: Di, body: StockRoutesListPayload
) -> StockItemsResponse[StockRoute]:
    return await op_routes_list(body, user=_user(), di=di)


@router.get("/routes/{route_id}", response_model=StockRoute)
async def routes_get(di: Di, route_id: str) -> StockRoute:
    return await op_routes_get(
        StockRouteIdPayload(route_id=route_id), user=_user(), di=di
    )


@router.post("/routes", response_model=StockRoute)
async def routes_create(
    di: Di, body: StockRouteCreatePayload
) -> StockRoute:
    return await op_routes_create(body, user=_user(), di=di)


@router.get("/container-types", response_model=StockItemsResponse[StockContainerType])
async def list_container_types(
    di: Di, warehouse_id: str
) -> StockItemsResponse[StockContainerType]:
    return await op_container_types_list(
        StockContainerTypesListPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.post("/container-types", response_model=StockContainerType)
async def create_container_type(
    di: Di, body: StockContainerTypeCreatePayload
) -> StockContainerType:
    return await op_container_types_create(body, user=_user(), di=di)


@router.patch(
    "/container-types/{container_type_id}", response_model=StockContainerType
)
async def update_container_type(
    di: Di, container_type_id: str, body: StockContainerTypeUpdatePayload
) -> StockContainerType:
    if body.container_type_id != container_type_id:
        raise_invalid(
            ValueError("container_type_id mismatch"),
            error_code="path_id_mismatch",
        )
    return await op_container_types_update(body, user=_user(), di=di)


@router.get("/resource-types", response_model=StockItemsResponse[StockResourceType])
async def list_resource_types(
    di: Di, warehouse_id: str
) -> StockItemsResponse[StockResourceType]:
    return await op_resource_types_list(
        StockResourceTypesListPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.post("/resource-types", response_model=StockResourceType)
async def create_resource_type(
    di: Di, body: StockResourceTypeCreatePayload
) -> StockResourceType:
    return await op_resource_types_create(body, user=_user(), di=di)


@router.patch(
    "/resource-types/{resource_type_id}", response_model=StockResourceType
)
async def update_resource_type(
    di: Di, resource_type_id: str, body: StockResourceTypeUpdatePayload
) -> StockResourceType:
    if body.resource_type_id != resource_type_id:
        raise_invalid(
            ValueError("resource_type_id mismatch"),
            error_code="path_id_mismatch",
        )
    return await op_resource_types_update(body, user=_user(), di=di)


@router.get("/resources", response_model=StockItemsResponse[StockResource])
async def list_resources(
    di: Di, warehouse_id: str
) -> StockItemsResponse[StockResource]:
    return await op_resources_list(
        StockResourcesListPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.post("/resources", response_model=StockResource)
async def create_resource(
    di: Di, body: StockResourceCreatePayload
) -> StockResource:
    return await op_resources_create(body, user=_user(), di=di)


@router.patch("/resources/{resource_id}", response_model=StockResource)
async def update_resource(
    di: Di, resource_id: str, body: StockResourceUpdatePayload
) -> StockResource:
    if body.resource_id != resource_id:
        raise_invalid(
            ValueError("resource_id mismatch"), error_code="path_id_mismatch"
        )
    return await op_resources_update(body, user=_user(), di=di)


@router.post("/resources/login", response_model=StockResource)
async def resource_login(
    di: Di, body: StockResourceLoginPayload
) -> StockResource:
    return await op_resources_login(body, user=_user(), di=di)


@router.post("/resources/logout", response_model=StockResourceLogoutResult)
async def resource_logout(
    di: Di, body: StockResourceLogoutPayload
) -> StockResourceLogoutResult:
    return await op_resources_logout(body, user=_user(), di=di)


@router.get("/containers", response_model=StockItemsResponse[StockLocation])
async def list_containers(
    di: Di,
    warehouse_id: str | None = None,
    parent_location_id: str | None = None,
) -> StockItemsResponse[StockLocation]:
    return await op_containers_list(
        StockContainersListPayload(
            warehouse_id=warehouse_id, parent_location_id=parent_location_id
        ),
        user=_user(),
        di=di,
    )


@router.post("/containers", response_model=StockLocation)
async def create_container(
    di: Di, body: StockContainerCreatePayload
) -> StockLocation:
    return await op_containers_create(body, user=_user(), di=di)


@router.get(
    "/containers/{container_id}", response_model=StockContainerContentsResponse
)
async def container_contents(
    di: Di, container_id: str
) -> StockContainerContentsResponse:
    return await op_containers_item(
        StockContainerIdPayload(container_id=container_id), user=_user(), di=di
    )


@router.post("/containers/{container_id}/move", response_model=StockLocation)
async def move_container(
    di: Di, container_id: str, body: StockContainerMovePayload
) -> StockLocation:
    if body.container_id != container_id:
        raise_invalid(ValueError("container_id mismatch"), error_code="path_id_mismatch")
    return await op_containers_move(body, user=_user(), di=di)


@router.get("/packagings", response_model=StockItemsResponse[CatalogPackagingView])
async def list_packagings(
    di: Di, product_id: str | None = None
) -> StockItemsResponse[CatalogPackagingView]:
    return await op_packagings_list(
        StockPackagingsListPayload(product_id=product_id), user=_user(), di=di
    )


@router.post("/packagings", response_model=CatalogPackagingView)
async def create_packaging(
    di: Di, body: StockPackagingCreatePayload
) -> CatalogPackagingView:
    return await op_packagings_create(body, user=_user(), di=di)


@router.delete("/packagings/{packaging_id}", response_model=CatalogPackagingView)
async def delete_packaging(
    di: Di, packaging_id: str
) -> CatalogPackagingView:
    return await op_packagings_delete(
        StockPackagingIdPayload(packaging_id=packaging_id), user=_user(), di=di
    )


@router.get("/uoms", response_model=StockItemsResponse[CatalogUom])
async def list_uoms(di: Di) -> StockItemsResponse[CatalogUom]:
    return await op_uoms_list(EmptyPayload(), user=_user(), di=di)


@router.get("/barcode/{barcode}", response_model=StockBarcodeResolveResponse)
async def resolve_barcode(di: Di, barcode: str) -> StockBarcodeResolveResponse:
    return await op_barcode_resolve(
        StockBarcodeResolvePayload(barcode=barcode), user=_user(), di=di
    )


# --- Скан-сессии ТСД ---


@router.post("/scan/open", response_model=StockScanOpenResponse)
async def scan_open(di: Di, body: StockScanOpenPayload) -> StockScanOpenResponse:
    return await op_scan_open(body, user=_user(), di=di)


@router.post("/scan/step", response_model=StockScanStepResponse)
async def scan_step(di: Di, body: StockScanStepPayload) -> StockScanStepResponse:
    return await op_scan_step(body, user=_user(), di=di)


@router.post("/scan/quantity", response_model=StockScanStepResponse)
async def scan_quantity(
    di: Di, body: StockScanQuantityPayload
) -> StockScanStepResponse:
    return await op_scan_quantity(body, user=_user(), di=di)


@router.post("/scan/commit", response_model=StockMove)
async def scan_commit(di: Di, body: StockScanCommitPayload) -> StockMove:
    return await op_scan_commit(body, user=_user(), di=di)


@router.post("/scan/count-commit", response_model=StockScanCountCommitResponse)
async def scan_count_commit(
    di: Di, body: StockScanCountCommitPayload
) -> StockScanCountCommitResponse:
    return await op_scan_count_commit(body, user=_user(), di=di)


@router.post("/scan/adhoc-commit", response_model=StockTransfer)
async def scan_adhoc_commit(
    di: Di, body: StockScanAdhocCommitPayload
) -> StockTransfer:
    return await op_scan_adhoc_commit(body, user=_user(), di=di)

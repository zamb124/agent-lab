"""REST-зеркало справочников stock: products/locations/warehouses/operation-types,
quants/valuation/lots/packages/uoms/pulse/barcode."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.stock.di import Di
from apps.stock.models import (
    StockLocation,
    StockLot,
    StockMove,
    StockOperationType,
    StockPackage,
    StockQuant,
    StockValueLayer,
    StockWarehouse,
    UnitOfMeasure,
)
from apps.stock.models.api import (
    StockBarcodeResolvePayload,
    StockBarcodeResolveResponse,
    StockItemsResponse,
    StockLocationCreatePayload,
    StockLocationIdPayload,
    StockLocationsListPayload,
    StockLocationUpdatePayload,
    StockLotCreatePayload,
    StockLotsListPayload,
    StockOperationTypesListPayload,
    StockOperationTypeUpdatePayload,
    StockPackageCreatePayload,
    StockPagePayload,
    StockProductCreatePayload,
    StockProductDetail,
    StockProductIdPayload,
    StockProductUpdatePayload,
    StockProductValueResponse,
    StockQuantInventoryApplyPayload,
    StockQuantInventorySetPayload,
    StockQuantsListPayload,
    StockValuationCorrectionPayload,
    StockValuationLayersPayload,
    StockValuationProductValuePayload,
    StockValuationRevaluePayload,
    StockWarehouseCreatePayload,
    StockWarehouseIdPayload,
    StockWarehousePulsePayload,
    StockWarehousePulseResponse,
    StockWarehouseUpdatePayload,
)
from apps.stock.realtime.operations import (
    op_barcode_resolve,
    op_locations_create,
    op_locations_item,
    op_locations_list,
    op_locations_update,
    op_lots_create,
    op_lots_list,
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
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import EmptyPayload, raise_invalid

router = APIRouter(tags=["stock-catalog"])


def _user():
    return require_context().user


# --- Products ---


@router.get("/products", response_model=OffsetPage[StockProductDetail])
async def list_products(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockProductDetail]:
    return await op_products_list(
        StockPagePayload(limit=limit, offset=offset), user=_user(), di=di
    )


@router.post("/products", response_model=StockProductDetail)
async def create_product(
    di: Di, body: StockProductCreatePayload
) -> StockProductDetail:
    return await op_products_create(body, user=_user(), di=di)


@router.get("/products/{product_id}", response_model=StockProductDetail)
async def get_product(di: Di, product_id: str) -> StockProductDetail:
    return await op_products_item(
        StockProductIdPayload(product_id=product_id), user=_user(), di=di
    )


@router.patch("/products/{product_id}", response_model=StockProductDetail)
async def update_product(
    di: Di, product_id: str, body: StockProductUpdatePayload
) -> StockProductDetail:
    if body.product_id != product_id:
        raise_invalid(ValueError("product_id mismatch"), error_code="path_id_mismatch")
    return await op_products_update(body, user=_user(), di=di)


# --- Locations ---


@router.get("/locations", response_model=StockItemsResponse[StockLocation])
async def list_locations(
    di: Di, warehouse_id: str | None = None
) -> StockItemsResponse[StockLocation]:
    return await op_locations_list(
        StockLocationsListPayload(warehouse_id=warehouse_id), user=_user(), di=di
    )


@router.post("/locations", response_model=StockLocation)
async def create_location(di: Di, body: StockLocationCreatePayload) -> StockLocation:
    return await op_locations_create(body, user=_user(), di=di)


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
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockQuant]:
    return await op_quants_list(
        StockQuantsListPayload(
            location_id=location_id,
            product_id=product_id,
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


@router.get("/valuation/layers", response_model=OffsetPage[StockValueLayer])
async def list_valuation_layers(
    di: Di,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockValueLayer]:
    return await op_valuation_layers_list(
        StockValuationLayersPayload(
            product_id=product_id,
            warehouse_id=warehouse_id,
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


# --- Lots / packages / uoms / barcode ---


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


@router.get("/packages", response_model=StockItemsResponse[StockPackage])
async def list_packages(di: Di) -> StockItemsResponse[StockPackage]:
    return await op_packages_list(EmptyPayload(), user=_user(), di=di)


@router.post("/packages", response_model=StockPackage)
async def create_package(di: Di, body: StockPackageCreatePayload) -> StockPackage:
    return await op_packages_create(body, user=_user(), di=di)


@router.get("/uoms", response_model=StockItemsResponse[UnitOfMeasure])
async def list_uoms(di: Di) -> StockItemsResponse[UnitOfMeasure]:
    return await op_uoms_list(EmptyPayload(), user=_user(), di=di)


@router.get("/barcode/{barcode}", response_model=StockBarcodeResolveResponse)
async def resolve_barcode(di: Di, barcode: str) -> StockBarcodeResolveResponse:
    return await op_barcode_resolve(
        StockBarcodeResolvePayload(barcode=barcode), user=_user(), di=di
    )

"""REST-зеркала команд geo: тонкая обвязка тех же `op_*`."""

from __future__ import annotations

from fastapi import APIRouter

from apps.geo.di import Di
from apps.geo.models.api import (
    GeoAddressesInZoneRequest,
    GeoAddressListResponse,
    GeoAddressNearestRequest,
    GeoAddressSuggestRequest,
    GeoImportStatusResponse,
    GeoIsochroneRequest,
    GeoIsochroneResponse,
    GeoRouteCalculateRequest,
    GeoRouteMatrixRequest,
    GeoRouteMatrixResponse,
    GeoRouteOrderRequest,
    GeoRouteOrderResponse,
    GeoRouteResponse,
)
from apps.geo.realtime.operations import (
    op_geo_addresses_in_zone,
    op_geo_addresses_nearest,
    op_geo_addresses_suggest,
    op_geo_import_status,
    op_geo_route_calculate,
    op_geo_route_isochrone,
    op_geo_route_matrix,
    op_geo_route_optimal_order,
)
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/v1", tags=["geo"])


@router.post("/addresses/in-zone", response_model=GeoAddressListResponse)
async def addresses_in_zone(
    payload: GeoAddressesInZoneRequest, di: Di
) -> GeoAddressListResponse:
    return await op_geo_addresses_in_zone(
        payload, user=require_context().user, di=di
    )


@router.post("/addresses/suggest", response_model=GeoAddressListResponse)
async def addresses_suggest(
    payload: GeoAddressSuggestRequest, di: Di
) -> GeoAddressListResponse:
    return await op_geo_addresses_suggest(
        payload, user=require_context().user, di=di
    )


@router.post("/addresses/nearest", response_model=GeoAddressListResponse)
async def addresses_nearest(
    payload: GeoAddressNearestRequest, di: Di
) -> GeoAddressListResponse:
    return await op_geo_addresses_nearest(
        payload, user=require_context().user, di=di
    )


@router.post("/route/calculate", response_model=GeoRouteResponse)
async def route_calculate(
    payload: GeoRouteCalculateRequest, di: Di
) -> GeoRouteResponse:
    return await op_geo_route_calculate(payload, user=require_context().user, di=di)


@router.post("/route/matrix", response_model=GeoRouteMatrixResponse)
async def route_matrix(payload: GeoRouteMatrixRequest, di: Di) -> GeoRouteMatrixResponse:
    return await op_geo_route_matrix(payload, user=require_context().user, di=di)


@router.post("/route/optimal-order", response_model=GeoRouteOrderResponse)
async def route_optimal_order(
    payload: GeoRouteOrderRequest, di: Di
) -> GeoRouteOrderResponse:
    return await op_geo_route_optimal_order(
        payload, user=require_context().user, di=di
    )


@router.post("/route/isochrone", response_model=GeoIsochroneResponse)
async def route_isochrone(
    payload: GeoIsochroneRequest, di: Di
) -> GeoIsochroneResponse:
    return await op_geo_route_isochrone(payload, user=require_context().user, di=di)


@router.get("/import/status", response_model=GeoImportStatusResponse)
async def import_status(di: Di) -> GeoImportStatusResponse:
    return await op_geo_import_status(
        EmptyPayload(), user=require_context().user, di=di
    )

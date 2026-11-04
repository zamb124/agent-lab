"""Каталог WS-команд сервиса geo."""

from apps.geo.di import GeoDi
from apps.geo.models.api import (
    GeoAddressesInZoneRequest,
    GeoAddressNearestRequest,
    GeoAddressSuggestRequest,
    GeoIsochroneRequest,
    GeoRouteCalculateRequest,
    GeoRouteMatrixRequest,
    GeoRouteOrderRequest,
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
from core.websocket import EmptyPayload
from core.websocket.operation import Operation, RegisteredOperation

GEO_OPERATIONS: dict[str, RegisteredOperation[GeoDi]] = {
    "geo/addresses/in_zone_requested": Operation(
        payload_model=GeoAddressesInZoneRequest, fn=op_geo_addresses_in_zone
    ),
    "geo/addresses/suggest_requested": Operation(
        payload_model=GeoAddressSuggestRequest, fn=op_geo_addresses_suggest
    ),
    "geo/addresses/nearest_requested": Operation(
        payload_model=GeoAddressNearestRequest, fn=op_geo_addresses_nearest
    ),
    "geo/route/calculate_requested": Operation(
        payload_model=GeoRouteCalculateRequest, fn=op_geo_route_calculate
    ),
    "geo/route/matrix_requested": Operation(
        payload_model=GeoRouteMatrixRequest, fn=op_geo_route_matrix
    ),
    "geo/route/optimal_order_requested": Operation(
        payload_model=GeoRouteOrderRequest, fn=op_geo_route_optimal_order
    ),
    "geo/route/isochrone_requested": Operation(
        payload_model=GeoIsochroneRequest, fn=op_geo_route_isochrone
    ),
    "geo/import/status_requested": Operation(
        payload_model=EmptyPayload, fn=op_geo_import_status
    ),
}

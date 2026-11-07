"""Каталог WS-команд сервиса geo."""

from apps.geo.di import GeoDi
from apps.geo.models.api import (
    GeoAddressCreateRequest,
    GeoAddressesInZoneRequest,
    GeoAddressNearestRequest,
    GeoAddressSuggestRequest,
    GeoAddressTargetRequest,
    GeoAddressUpdateRequest,
    GeoCursorResetRequest,
    GeoEdgeCloseRequest,
    GeoEdgeTargetRequest,
    GeoEnrichListRequest,
    GeoEnrichRetryRequest,
    GeoFeaturesRequest,
    GeoFeatureSuppressRequest,
    GeoImportRunRequest,
    GeoIsochroneRequest,
    GeoOverridesListRequest,
    GeoRegionNameRequest,
    GeoRegionUpsertRequest,
    GeoRouteCalculateRequest,
    GeoRouteMatrixRequest,
    GeoRouteOrderRequest,
)
from apps.geo.realtime.operations import (
    op_geo_addresses_create,
    op_geo_addresses_in_zone,
    op_geo_addresses_nearest,
    op_geo_addresses_override_revert,
    op_geo_addresses_remove,
    op_geo_addresses_suggest,
    op_geo_addresses_update,
    op_geo_cursors_list,
    op_geo_cursors_reset,
    op_geo_edges_close,
    op_geo_edges_open,
    op_geo_enrich_list,
    op_geo_enrich_retry,
    op_geo_features_suppress,
    op_geo_features_unsuppress,
    op_geo_import_run,
    op_geo_import_status,
    op_geo_layers_features,
    op_geo_layers_list,
    op_geo_overrides_list,
    op_geo_regions_create,
    op_geo_regions_list,
    op_geo_regions_remove,
    op_geo_regions_update,
    op_geo_route_calculate,
    op_geo_route_isochrone,
    op_geo_route_matrix,
    op_geo_route_optimal_order,
    op_geo_sources_list,
    op_geo_stats_overview,
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
    "geo/import/run_requested": Operation(
        payload_model=GeoImportRunRequest, fn=op_geo_import_run
    ),
    "geo/regions/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_geo_regions_list
    ),
    "geo/regions/create_requested": Operation(
        payload_model=GeoRegionUpsertRequest, fn=op_geo_regions_create
    ),
    "geo/regions/update_requested": Operation(
        payload_model=GeoRegionUpsertRequest, fn=op_geo_regions_update
    ),
    "geo/regions/remove_requested": Operation(
        payload_model=GeoRegionNameRequest, fn=op_geo_regions_remove
    ),
    "geo/sources/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_geo_sources_list
    ),
    "geo/stats/overview_requested": Operation(
        payload_model=EmptyPayload, fn=op_geo_stats_overview
    ),
    "geo/cursors/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_geo_cursors_list
    ),
    "geo/cursors/reset_requested": Operation(
        payload_model=GeoCursorResetRequest, fn=op_geo_cursors_reset
    ),
    "geo/enrich/list_requested": Operation(
        payload_model=GeoEnrichListRequest, fn=op_geo_enrich_list
    ),
    "geo/enrich/retry_requested": Operation(
        payload_model=GeoEnrichRetryRequest, fn=op_geo_enrich_retry
    ),
    "geo/layers/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_geo_layers_list
    ),
    "geo/layers/features_requested": Operation(
        payload_model=GeoFeaturesRequest, fn=op_geo_layers_features
    ),
    "geo/addresses/create_requested": Operation(
        payload_model=GeoAddressCreateRequest, fn=op_geo_addresses_create
    ),
    "geo/addresses/update_requested": Operation(
        payload_model=GeoAddressUpdateRequest, fn=op_geo_addresses_update
    ),
    "geo/addresses/remove_requested": Operation(
        payload_model=GeoAddressTargetRequest, fn=op_geo_addresses_remove
    ),
    "geo/addresses/override_revert_requested": Operation(
        payload_model=GeoAddressTargetRequest,
        fn=op_geo_addresses_override_revert,
    ),
    "geo/overrides/list_requested": Operation(
        payload_model=GeoOverridesListRequest, fn=op_geo_overrides_list
    ),
    "geo/features/suppress_requested": Operation(
        payload_model=GeoFeatureSuppressRequest, fn=op_geo_features_suppress
    ),
    "geo/features/unsuppress_requested": Operation(
        payload_model=GeoFeatureSuppressRequest, fn=op_geo_features_unsuppress
    ),
    "geo/edges/close_requested": Operation(
        payload_model=GeoEdgeCloseRequest, fn=op_geo_edges_close
    ),
    "geo/edges/open_requested": Operation(
        payload_model=GeoEdgeTargetRequest, fn=op_geo_edges_open
    ),
}

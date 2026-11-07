"""REST-зеркала команд geo: тонкая обвязка тех же `op_*`."""

from __future__ import annotations

from fastapi import APIRouter

from apps.geo.di import Di
from apps.geo.models.api import (
    GeoAddressCreateRequest,
    GeoAddressesInZoneRequest,
    GeoAddressHit,
    GeoAddressListResponse,
    GeoAddressNearestRequest,
    GeoAddressSuggestRequest,
    GeoAddressTargetRequest,
    GeoAddressUpdateRequest,
    GeoCursorItem,
    GeoCursorListResponse,
    GeoCursorResetRequest,
    GeoEdgeCloseRequest,
    GeoEdgeTargetRequest,
    GeoEnrichItemResponse,
    GeoEnrichListRequest,
    GeoEnrichListResponse,
    GeoEnrichRetryRequest,
    GeoFeatureCollectionResponse,
    GeoFeaturesRequest,
    GeoFeatureSuppressRequest,
    GeoImportRunRequest,
    GeoImportRunResponse,
    GeoImportStatusResponse,
    GeoIsochroneRequest,
    GeoIsochroneResponse,
    GeoLayerListResponse,
    GeoOverrideListResponse,
    GeoOverridesListRequest,
    GeoRegionItem,
    GeoRegionListResponse,
    GeoRegionNameRequest,
    GeoRegionUpsertRequest,
    GeoRouteCalculateRequest,
    GeoRouteMatrixRequest,
    GeoRouteMatrixResponse,
    GeoRouteOrderRequest,
    GeoRouteOrderResponse,
    GeoRouteResponse,
    GeoSourceListResponse,
    GeoStatsOverview,
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
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(tags=["geo"])


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


@router.post("/import/run", response_model=GeoImportRunResponse)
async def import_run(payload: GeoImportRunRequest, di: Di) -> GeoImportRunResponse:
    return await op_geo_import_run(payload, user=require_context().user, di=di)


@router.get("/regions", response_model=GeoRegionListResponse)
async def regions_list(di: Di) -> GeoRegionListResponse:
    return await op_geo_regions_list(EmptyPayload(), user=require_context().user, di=di)


@router.post("/regions", response_model=GeoRegionItem)
async def regions_create(
    payload: GeoRegionUpsertRequest, di: Di
) -> GeoRegionItem:
    return await op_geo_regions_create(payload, user=require_context().user, di=di)


@router.put("/regions/{name}", response_model=GeoRegionItem)
async def regions_update(
    name: str, payload: GeoRegionUpsertRequest, di: Di
) -> GeoRegionItem:
    body = payload.model_copy(update={"name": name})
    return await op_geo_regions_update(body, user=require_context().user, di=di)


@router.delete("/regions/{name}", response_model=EmptyPayload)
async def regions_remove(name: str, di: Di) -> EmptyPayload:
    return await op_geo_regions_remove(
        GeoRegionNameRequest(name=name), user=require_context().user, di=di
    )


@router.get("/sources", response_model=GeoSourceListResponse)
async def sources_list(di: Di) -> GeoSourceListResponse:
    return await op_geo_sources_list(EmptyPayload(), user=require_context().user, di=di)


@router.get("/stats/overview", response_model=GeoStatsOverview)
async def stats_overview(di: Di) -> GeoStatsOverview:
    return await op_geo_stats_overview(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.get("/cursors", response_model=GeoCursorListResponse)
async def cursors_list(di: Di) -> GeoCursorListResponse:
    return await op_geo_cursors_list(EmptyPayload(), user=require_context().user, di=di)


@router.post("/cursors/reset", response_model=GeoCursorItem)
async def cursors_reset(
    payload: GeoCursorResetRequest, di: Di
) -> GeoCursorItem:
    return await op_geo_cursors_reset(payload, user=require_context().user, di=di)


@router.post("/enrich/list", response_model=GeoEnrichListResponse)
async def enrich_list(
    payload: GeoEnrichListRequest, di: Di
) -> GeoEnrichListResponse:
    return await op_geo_enrich_list(payload, user=require_context().user, di=di)


@router.post("/enrich/retry", response_model=GeoEnrichItemResponse)
async def enrich_retry(
    payload: GeoEnrichRetryRequest, di: Di
) -> GeoEnrichItemResponse:
    return await op_geo_enrich_retry(payload, user=require_context().user, di=di)


@router.get("/layers", response_model=GeoLayerListResponse)
async def layers_list(di: Di) -> GeoLayerListResponse:
    return await op_geo_layers_list(EmptyPayload(), user=require_context().user, di=di)


@router.post("/layers/features", response_model=GeoFeatureCollectionResponse)
async def layers_features(
    payload: GeoFeaturesRequest, di: Di
) -> GeoFeatureCollectionResponse:
    return await op_geo_layers_features(payload, user=require_context().user, di=di)


@router.post("/addresses/create", response_model=GeoAddressHit)
async def addresses_create(
    payload: GeoAddressCreateRequest, di: Di
) -> GeoAddressHit:
    return await op_geo_addresses_create(payload, user=require_context().user, di=di)


@router.post("/addresses/update", response_model=GeoAddressHit)
async def addresses_update(
    payload: GeoAddressUpdateRequest, di: Di
) -> GeoAddressHit:
    return await op_geo_addresses_update(payload, user=require_context().user, di=di)


@router.post("/addresses/remove", response_model=EmptyPayload)
async def addresses_remove(
    payload: GeoAddressTargetRequest, di: Di
) -> EmptyPayload:
    return await op_geo_addresses_remove(payload, user=require_context().user, di=di)


@router.post("/addresses/override-revert", response_model=GeoAddressHit | None)
async def addresses_override_revert(
    payload: GeoAddressTargetRequest, di: Di
) -> GeoAddressHit | None:
    return await op_geo_addresses_override_revert(
        payload, user=require_context().user, di=di
    )


@router.post("/overrides/list", response_model=GeoOverrideListResponse)
async def overrides_list(
    payload: GeoOverridesListRequest, di: Di
) -> GeoOverrideListResponse:
    return await op_geo_overrides_list(payload, user=require_context().user, di=di)


@router.post("/features/suppress", response_model=EmptyPayload)
async def features_suppress(
    payload: GeoFeatureSuppressRequest, di: Di
) -> EmptyPayload:
    return await op_geo_features_suppress(
        payload, user=require_context().user, di=di
    )


@router.post("/features/unsuppress", response_model=EmptyPayload)
async def features_unsuppress(
    payload: GeoFeatureSuppressRequest, di: Di
) -> EmptyPayload:
    return await op_geo_features_unsuppress(
        payload, user=require_context().user, di=di
    )


@router.post("/edges/close", response_model=EmptyPayload)
async def edges_close(payload: GeoEdgeCloseRequest, di: Di) -> EmptyPayload:
    return await op_geo_edges_close(payload, user=require_context().user, di=di)


@router.post("/edges/open", response_model=EmptyPayload)
async def edges_open(payload: GeoEdgeTargetRequest, di: Di) -> EmptyPayload:
    return await op_geo_edges_open(payload, user=require_context().user, di=di)

"""Бизнес-функции geo: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import json
from collections.abc import Awaitable

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
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.geo_coverage_service import GeoCoverageError
from apps.geo.services.geo_routing_service import GeoRoutingError
from apps.geo.tasks.task_names import (
    GEO_DATAMOS_SYNC,
    GEO_ENRICH_TICK,
    GEO_GAR_SYNC,
    GEO_NSPD_CRAWL,
    GEO_OSM_DIFF_TICK,
    GEO_OSM_SYNC_TICK,
    GEO_OVERTURE_SYNC,
    GEO_TILES_SYNC,
)
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.models.identity_models import User
from core.request_scope import require_company, require_company_admin
from core.tasks import enqueue
from core.types import JsonObject
from core.utils.geo import is_valid_delivery_zone
from core.websocket import EmptyPayload
from core.websocket.operation import (
    raise_conflict,
    raise_invalid,
    raise_not_found,
    raise_unavailable,
)


def _validate_zone(zone: JsonObject | None) -> str | None:
    """GeoJSON-строка полигона или ``None`` при пустой зоне."""
    if zone is None:
        return None
    if not is_valid_delivery_zone(zone):
        raise_invalid(ValueError("invalid zone"), error_code="invalid_delivery_zone")
    return json.dumps(zone)


async def _routing[T](call: Awaitable[T]) -> T:
    """Граница ошибок роутинга: доменные исключения → коды транспорта."""
    try:
        return await call
    except GeoRoutingError as exc:
        raise_invalid(exc, error_code=exc.code)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformUnavailableError as exc:
        raise_unavailable(exc)


async def _coverage[T](call: Awaitable[T]) -> T:
    """Граница ошибок реестра покрытия: доменные исключения → коды транспорта."""
    try:
        return await call
    except GeoCoverageError as exc:
        raise_invalid(exc, error_code=exc.code)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)


IMPORT_RUN_SPECS = {
    "osm": GEO_OSM_SYNC_TICK,
    "gar": GEO_GAR_SYNC,
    "nspd": GEO_NSPD_CRAWL,
    "data_mos_ru": GEO_DATAMOS_SYNC,
    "overture": GEO_OVERTURE_SYNC,
    "geofabrik": GEO_OSM_DIFF_TICK,
    "enrich": GEO_ENRICH_TICK,
    "tiles": GEO_TILES_SYNC,
}
"""``geo/import/run`` — запуск конкретного источника по имени из реестра.

Кроме источников принимает служебные цели: ``enrich`` — немедленный дрейн
очереди обогащения, ``tiles`` — синк базовой карты (basemap PMTiles).
``manual`` намеренно отсутствует — слой админ-правок без краулера."""


async def op_geo_addresses_in_zone(
    payload: GeoAddressesInZoneRequest, *, user: User, di: Di
) -> GeoAddressListResponse:
    _ = require_company()
    _ = user
    zone = _validate_zone(payload.zone)
    assert zone is not None
    limit = min(payload.limit, di.settings.zone_addresses_limit_max)
    return await di.geo_address_service.addresses_in_zone_by_name_asc(
        zone_geojson=zone, query=payload.q, limit=limit, offset=payload.offset
    )


async def op_geo_addresses_suggest(
    payload: GeoAddressSuggestRequest, *, user: User, di: Di
) -> GeoAddressListResponse:
    _ = require_company()
    _ = user
    zone = _validate_zone(payload.zone)
    limit = min(payload.limit, di.settings.suggest_limit_max)
    items = await di.geo_address_service.suggest_by_score_desc(
        query=payload.q,
        zone_geojson=zone,
        lat=payload.lat,
        lng=payload.lng,
        limit=limit,
    )
    return GeoAddressListResponse(items=items, total=len(items))


async def op_geo_addresses_nearest(
    payload: GeoAddressNearestRequest, *, user: User, di: Di
) -> GeoAddressListResponse:
    _ = require_company()
    _ = user
    items = await di.geo_address_service.nearest_by_distance(
        lat=payload.lat, lng=payload.lng, limit=payload.limit
    )
    return GeoAddressListResponse(items=items, total=len(items))


async def op_geo_route_calculate(
    payload: GeoRouteCalculateRequest, *, user: User, di: Di
) -> GeoRouteResponse:
    _ = require_company()
    _ = user
    return await _routing(
        di.geo_routing_service.calculate(
            from_lat=payload.from_point.lat,
            from_lng=payload.from_point.lng,
            to_lat=payload.to_point.lat,
            to_lng=payload.to_point.lng,
            mode=payload.mode,
        )
    )


async def op_geo_route_matrix(
    payload: GeoRouteMatrixRequest, *, user: User, di: Di
) -> GeoRouteMatrixResponse:
    _ = require_company()
    _ = user
    return await _routing(
        di.geo_routing_service.matrix(
            sources=[(p.lat, p.lng) for p in payload.sources],
            targets=[(p.lat, p.lng) for p in payload.targets],
            mode=payload.mode,
        )
    )


async def op_geo_route_optimal_order(
    payload: GeoRouteOrderRequest, *, user: User, di: Di
) -> GeoRouteOrderResponse:
    _ = require_company()
    _ = user
    return await _routing(
        di.geo_routing_service.optimal_order(
            start=(payload.start.lat, payload.start.lng),
            points=[(p.lat, p.lng) for p in payload.points],
            mode=payload.mode,
            with_legs=payload.legs,
        )
    )


async def op_geo_route_isochrone(
    payload: GeoIsochroneRequest, *, user: User, di: Di
) -> GeoIsochroneResponse:
    _ = require_company()
    _ = user
    return await _routing(
        di.geo_routing_service.isochrone(
            lat=payload.center.lat,
            lng=payload.center.lng,
            minutes=payload.minutes,
            mode=payload.mode,
        )
    )


async def op_geo_import_status(
    payload: EmptyPayload, *, user: User, di: Di
) -> GeoImportStatusResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    _ = payload
    state = await GeoImportState.get_state()
    if state is None:
        return GeoImportStatusResponse(current_generation=0, status="idle")
    return GeoImportStatusResponse(
        current_generation=state.current_generation,
        status=state.status.value,
        source_name=state.source_name,
        source_modified_at=(
            state.source_modified_at.isoformat() if state.source_modified_at else None
        ),
        rows_addresses=state.rows_addresses,
        rows_vertices=state.rows_vertices,
        rows_edges=state.rows_edges,
        rows_restrictions=state.rows_restrictions,
        last_error=state.last_error,
        finished_at=state.finished_at.isoformat() if state.finished_at else None,
    )


async def op_geo_import_run(
    payload: GeoImportRunRequest, *, user: User, di: Di
) -> GeoImportRunResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    source = payload.source.strip() or "osm"
    spec = IMPORT_RUN_SPECS.get(source)
    if spec is None:
        raise_invalid(
            ValueError(f"unknown import source {source!r}"),
            error_code="geo_import_source_unknown",
        )
    _ = await enqueue(spec)
    return GeoImportRunResponse(enqueued=True, source=source)


async def op_geo_regions_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> GeoRegionListResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    _ = payload
    return await di.geo_coverage_service.regions_response()


async def op_geo_regions_create(
    payload: GeoRegionUpsertRequest, *, user: User, di: Di
) -> GeoRegionItem:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await _coverage(di.geo_coverage_service.create_region(payload))


async def op_geo_regions_update(
    payload: GeoRegionUpsertRequest, *, user: User, di: Di
) -> GeoRegionItem:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await _coverage(di.geo_coverage_service.update_region(payload))


async def op_geo_regions_remove(
    payload: GeoRegionNameRequest, *, user: User, di: Di
) -> EmptyPayload:
    _ = await require_company_admin(di.authz_service)
    _ = user
    await _coverage(di.geo_coverage_service.delete_region(payload.name))
    return EmptyPayload()


async def op_geo_sources_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> GeoSourceListResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    _ = payload
    return await di.geo_coverage_service.sources_response()


async def op_geo_stats_overview(
    payload: EmptyPayload, *, user: User, di: Di
) -> GeoStatsOverview:
    _ = await require_company_admin(di.authz_service)
    _ = user
    _ = payload
    return await di.geo_coverage_service.stats_overview()


async def op_geo_cursors_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> GeoCursorListResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    _ = payload
    return await di.geo_coverage_service.cursors_response()


async def op_geo_enrich_list(
    payload: GeoEnrichListRequest, *, user: User, di: Di
) -> GeoEnrichListResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await di.geo_coverage_service.enrich_list_response(
        status=payload.status, limit=payload.limit, offset=payload.offset
    )


async def op_geo_cursors_reset(
    payload: GeoCursorResetRequest, *, user: User, di: Di
) -> GeoCursorItem:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await _coverage(
        di.geo_coverage_service.reset_cursor(
            source=payload.source, region=payload.region
        )
    )


async def op_geo_enrich_retry(
    payload: GeoEnrichRetryRequest, *, user: User, di: Di
) -> GeoEnrichItemResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await _coverage(
        di.geo_coverage_service.retry_enrich(item_id=payload.item_id)
    )


async def op_geo_layers_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> GeoLayerListResponse:
    _ = require_company()
    _ = user
    _ = payload
    return await di.geo_layer_service.layers_response()


async def op_geo_layers_features(
    payload: GeoFeaturesRequest, *, user: User, di: Di
) -> GeoFeatureCollectionResponse:
    _ = require_company()
    _ = user
    return await _coverage(
        di.geo_layer_service.features_response(
            south=payload.south,
            west=payload.west,
            north=payload.north,
            east=payload.east,
            zoom=payload.zoom,
            layer_names=payload.layers,
        )
    )


async def op_geo_addresses_create(
    payload: GeoAddressCreateRequest, *, user: User, di: Di
) -> GeoAddressHit:
    scope = await require_company_admin(di.authz_service)
    _ = user
    return await di.geo_admin_service.create_address(
        display_name=payload.display_name,
        city=payload.city,
        street=payload.street,
        housenumber=payload.housenumber,
        postcode=payload.postcode,
        lat=payload.lat,
        lng=payload.lng,
        region=payload.region,
        user_id=scope.user_id,
    )


async def _admin[T](call: Awaitable[T]) -> T:
    """Граница ошибок админ-правок: доменные исключения → коды транспорта."""
    try:
        return await call
    except PlatformNotFoundError as exc:
        raise_not_found(exc)


async def op_geo_addresses_update(
    payload: GeoAddressUpdateRequest, *, user: User, di: Di
) -> GeoAddressHit:
    scope = await require_company_admin(di.authz_service)
    _ = user
    return await _admin(
        di.geo_admin_service.update_address(payload, user_id=scope.user_id)
    )


async def op_geo_addresses_remove(
    payload: GeoAddressTargetRequest, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _admin(
        di.geo_admin_service.remove_address(
            osm_type=payload.osm_type,
            osm_id=payload.osm_id,
            reason=payload.reason,
            user_id=scope.user_id,
        )
    )
    return EmptyPayload()


async def op_geo_addresses_override_revert(
    payload: GeoAddressTargetRequest, *, user: User, di: Di
) -> GeoAddressHit | None:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await _admin(
        di.geo_admin_service.revert_override(
            osm_type=payload.osm_type, osm_id=payload.osm_id
        )
    )


async def op_geo_overrides_list(
    payload: GeoOverridesListRequest, *, user: User, di: Di
) -> GeoOverrideListResponse:
    _ = await require_company_admin(di.authz_service)
    _ = user
    return await di.geo_admin_service.overrides_page_desc(
        limit=payload.limit, offset=payload.offset
    )


async def op_geo_features_suppress(
    payload: GeoFeatureSuppressRequest, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    await di.geo_admin_service.suppress_feature(
        entity=payload.entity,
        osm_id=payload.osm_id,
        reason=payload.reason,
        user_id=scope.user_id,
    )
    return EmptyPayload()


async def op_geo_features_unsuppress(
    payload: GeoFeatureSuppressRequest, *, user: User, di: Di
) -> EmptyPayload:
    _ = await require_company_admin(di.authz_service)
    _ = user
    await _admin(
        di.geo_admin_service.unsuppress_feature(
            entity=payload.entity, osm_id=payload.osm_id
        )
    )
    return EmptyPayload()


async def op_geo_edges_close(
    payload: GeoEdgeCloseRequest, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    await di.geo_admin_service.close_way(
        osm_way_id=payload.osm_way_id,
        modes=payload.modes,
        reason=payload.reason,
        user_id=scope.user_id,
    )
    return EmptyPayload()


async def op_geo_edges_open(
    payload: GeoEdgeTargetRequest, *, user: User, di: Di
) -> EmptyPayload:
    _ = await require_company_admin(di.authz_service)
    _ = user
    await _admin(di.geo_admin_service.open_way(osm_way_id=payload.osm_way_id))
    return EmptyPayload()

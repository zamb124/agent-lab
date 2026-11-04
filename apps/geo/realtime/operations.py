"""Бизнес-функции geo: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import json
from collections.abc import Awaitable

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
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.geo_routing_service import GeoRoutingError
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError
from core.models.identity_models import User
from core.request_scope import require_company, require_company_admin
from core.types import JsonObject
from core.utils.geo import is_valid_delivery_zone
from core.websocket import EmptyPayload
from core.websocket.operation import (
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
        last_error=state.last_error,
        finished_at=state.finished_at.isoformat() if state.finished_at else None,
    )

"""Типизированные модели Geo API (межсервисный контракт ``geo/api/v1``)."""

from __future__ import annotations

from typing import Literal

from core.models import StrictBaseModel
from core.types import JsonObject


class GeoAddressHit(StrictBaseModel):
    """Адрес из справочника geo."""

    id: int
    osm_type: str
    osm_id: int
    display_name: str
    city: str = ""
    street: str = ""
    housenumber: str = ""
    postcode: str = ""
    lat: float
    lng: float
    # Заполняет только /addresses/nearest — дистанция от запрошенной точки, м.
    distance_m: float | None = None


class GeoAddressListResult(StrictBaseModel):
    items: list[GeoAddressHit]
    total: int


class GeoRouteResult(StrictBaseModel):
    distance_m: float
    duration_s: float
    geometry: JsonObject | None = None
    # Сторона улицы точки прибытия — см. GeoRouteResponse в apps/geo.
    arrival_side: Literal["left", "right"] | None = None


class GeoMatrixResult(StrictBaseModel):
    durations_s: list[list[float | None]]
    distances_m: list[list[float | None]]


class GeoOrderLegResult(StrictBaseModel):
    from_index: int
    to_index: int
    distance_m: float
    duration_s: float
    geometry: JsonObject | None = None


class GeoOrderResult(StrictBaseModel):
    order: list[int]
    total_distance_m: float
    total_duration_s: float
    legs: list[GeoOrderLegResult] = []


class GeoIsochroneResult(StrictBaseModel):
    polygon: JsonObject | None = None
    reachable_vertices: int


class GeoImportStatusResult(StrictBaseModel):
    current_generation: int
    status: str
    source_name: str = ""
    source_modified_at: str | None = None
    rows_addresses: int = 0
    rows_vertices: int = 0
    rows_edges: int = 0
    last_error: str = ""
    finished_at: str | None = None

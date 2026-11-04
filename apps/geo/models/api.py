"""Pydantic-модели API/WS домена geo."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject

RouteMode = Literal["car", "foot"]


class GeoPoint(StrictBaseModel):
    """Точка WGS84."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class GeoAddressHit(StrictBaseModel):
    """Адрес из справочника."""

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


class GeoAddressesInZoneRequest(StrictBaseModel):
    """Постраничный список адресов внутри полигона (GeoJSON Polygon)."""

    zone: JsonObject
    q: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class GeoAddressListResponse(StrictBaseModel):
    items: list[GeoAddressHit]
    total: int


class GeoAddressSuggestRequest(StrictBaseModel):
    """Автокомплит адреса; ``zone`` опционально сужает выдачу полигоном."""

    q: str = Field(min_length=2, max_length=200)
    zone: JsonObject | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    limit: int = Field(default=10, ge=1, le=20)


class GeoAddressNearestRequest(StrictBaseModel):
    """Ближайшие адреса к точке."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    limit: int = Field(default=10, ge=1, le=50)


class GeoRouteCalculateRequest(StrictBaseModel):
    """Кратчайший путь между двумя точками по дорогам."""

    from_point: GeoPoint
    to_point: GeoPoint
    mode: RouteMode = "car"


class GeoRouteResponse(StrictBaseModel):
    distance_m: float
    duration_s: float
    geometry: JsonObject | None = None


class GeoRouteMatrixRequest(StrictBaseModel):
    """Матрица N×M по дорогам; ячейки — duration_s / distance_m."""

    sources: list[GeoPoint] = Field(min_length=1)
    targets: list[GeoPoint] = Field(min_length=1)
    mode: RouteMode = "car"


class GeoRouteMatrixResponse(StrictBaseModel):
    durations_s: list[list[float | None]]
    distances_m: list[list[float | None]]


class GeoRouteOrderRequest(StrictBaseModel):
    """Оптимальный порядок объезда точек из старта и обратно (TSP)."""

    start: GeoPoint
    points: list[GeoPoint] = Field(min_length=1)
    mode: RouteMode = "car"
    legs: bool = False


class GeoRouteLeg(StrictBaseModel):
    """Плечо маршрута; индексы ``-1`` — стартовая точка, остальные — ``points``."""

    from_index: int
    to_index: int
    distance_m: float
    duration_s: float
    geometry: JsonObject | None = None


class GeoRouteOrderResponse(StrictBaseModel):
    """``order`` — индексы в ``points`` в оптимальном порядке объезда."""

    order: list[int]
    total_distance_m: float
    total_duration_s: float
    legs: list[GeoRouteLeg] = Field(default_factory=list)


class GeoIsochroneRequest(StrictBaseModel):
    """Полигон достижимости за N минут от точки."""

    center: GeoPoint
    minutes: float = Field(gt=0, le=120)
    mode: RouteMode = "car"


class GeoIsochroneResponse(StrictBaseModel):
    polygon: JsonObject | None = None
    reachable_vertices: int


class GeoImportStatusResponse(StrictBaseModel):
    """Состояние конвейера импорта OSM-данных."""

    current_generation: int
    status: str
    source_name: str = ""
    source_modified_at: str | None = None
    rows_addresses: int = 0
    rows_vertices: int = 0
    rows_edges: int = 0
    last_error: str = ""
    finished_at: str | None = None

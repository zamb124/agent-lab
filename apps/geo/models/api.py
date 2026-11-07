"""Pydantic-модели API/WS домена geo."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from apps.geo.models.geo_enrich_item import GeoEnrichStatus
from apps.geo.models.geo_region import GeoRegionKind
from core.models import StrictBaseModel
from core.types import JsonObject

RouteMode = Literal["car", "foot", "bike", "scooter"]


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
    # Заполняет только /addresses/nearest — дистанция от запрошенной точки, м.
    distance_m: float | None = None


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
    # Сторона улицы точки прибытия относительно направления движения —
    # подсказка курьеру, с какой стороны дом; None — привязка в вершину.
    arrival_side: Literal["left", "right"] | None = None


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
    rows_restrictions: int = 0
    rows_barriers: int = 0
    rows_signals: int = 0
    last_error: str = ""
    finished_at: str | None = None


class GeoBbox(StrictBaseModel):
    """Прямоугольная рамка WGS84: south/west — минимальный угол."""

    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)


class GeoRegionUpsertRequest(StrictBaseModel):
    """Полная форма региона покрытия; ``name`` — slug-ключ."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(default="", max_length=255)
    kind: GeoRegionKind = GeoRegionKind.CITY
    bbox: GeoBbox
    extract_urls: list[str] = Field(default_factory=list, max_length=20)
    replication_url: str = Field(default="", max_length=2048)
    enabled: bool = True


class GeoRegionItem(StrictBaseModel):
    """Регион покрытия со счётчиками активного поколения."""

    id: int
    name: str
    title: str
    kind: str
    bbox: GeoBbox
    extract_urls: list[str]
    replication_url: str
    enabled: bool
    last_imported_at: str | None = None
    addresses: int = 0
    vertices: int = 0
    edges: int = 0


class GeoRegionListResponse(StrictBaseModel):
    items: list[GeoRegionItem]
    generation: int


class GeoRegionNameRequest(StrictBaseModel):
    """Операция над регионом по slug-имени."""

    name: str = Field(min_length=1, max_length=64)


class GeoSourceItem(StrictBaseModel):
    """Источник из allowlist-реестра с лицензией."""

    id: int
    name: str
    title: str
    kind: str
    license: str
    attribution: str
    url: str
    enabled: bool


class GeoSourceListResponse(StrictBaseModel):
    items: list[GeoSourceItem]


class GeoStatsRow(StrictBaseModel):
    """Счётчик сущности в поколении по источнику и региону."""

    source: str
    region: str
    entity: str
    rows: int


class GeoStatsOverview(StrictBaseModel):
    """Сводка загруженных данных активного поколения."""

    generation: int
    rows: list[GeoStatsRow]
    totals: dict[str, int]


class GeoCursorItem(StrictBaseModel):
    """Позиция чанкового потока источника."""

    source: str
    region: str
    cursor: str
    status: str
    rows_done: int
    last_error: str
    updated_at: str


class GeoCursorListResponse(StrictBaseModel):
    items: list[GeoCursorItem]


class GeoCursorResetRequest(StrictBaseModel):
    """Сброс курсора потока источника: следующий тик начнёт проход заново."""

    source: str = Field(min_length=1, max_length=64)
    region: str = Field(default="", max_length=64)


class GeoEnrichListRequest(StrictBaseModel):
    """Страница очереди обогащения; ``status`` — необязательный фильтр."""

    status: GeoEnrichStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GeoEnrichItemResponse(StrictBaseModel):
    id: int
    kind: str
    payload: JsonObject
    priority: int
    status: str
    attempts: int
    last_error: str
    created_at: str
    done_at: str | None = None


class GeoEnrichListResponse(StrictBaseModel):
    items: list[GeoEnrichItemResponse]
    pending: int


class GeoEnrichRetryRequest(StrictBaseModel):
    """Повтор failed-элемента очереди обогащения."""

    item_id: int = Field(ge=1)


class GeoImportRunRequest(StrictBaseModel):
    """Внеочередной тик источника; пустой ``source`` → OSM (дефолт)."""

    source: str = Field(default="", max_length=32)


class GeoImportRunResponse(StrictBaseModel):
    """Постановка внеочередного тика синхронизации."""

    enqueued: bool
    source: str = ""


class GeoLayerInfo(StrictBaseModel):
    """Канонический слой карты: метаданные и число фич активного поколения."""

    name: str
    geometry: str
    min_zoom: int
    max_features: int
    color: str
    features: int = 0


class GeoLayerListResponse(StrictBaseModel):
    layers: list[GeoLayerInfo]
    generation: int


class GeoFeaturesRequest(StrictBaseModel):
    """Фичи слоёв в рамке карты; ``layers`` пуст — все слои реестра."""

    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    zoom: int = Field(ge=0, le=22)
    layers: list[str] = Field(default_factory=list, max_length=16)


class GeoFeature(StrictBaseModel):
    """GeoJSON-фича канонического слоя."""

    layer: str
    id: str
    geometry: JsonObject
    properties: JsonObject


class GeoFeatureCollectionResponse(StrictBaseModel):
    features: list[GeoFeature]
    truncated: bool = False


class GeoAddressCreateRequest(StrictBaseModel):
    """Ручной адрес: evergreen-строка ``generation=0``, ``osm_type='manual'``."""

    display_name: str = Field(min_length=1, max_length=500)
    city: str = Field(default="", max_length=255)
    street: str = Field(default="", max_length=255)
    housenumber: str = Field(default="", max_length=64)
    postcode: str = Field(default="", max_length=32)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    region: str = Field(default="", max_length=64)
    reason: str = Field(default="", max_length=500)


class GeoAddressUpdateRequest(StrictBaseModel):
    """Патч админа к адресу; ``None``-поле не меняет значение."""

    osm_type: str = Field(min_length=1, max_length=16)
    osm_id: int
    display_name: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=255)
    street: str | None = Field(default=None, max_length=255)
    housenumber: str | None = Field(default=None, max_length=64)
    postcode: str | None = Field(default=None, max_length=32)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    reason: str = Field(default="", max_length=500)


class GeoAddressTargetRequest(StrictBaseModel):
    """Операция над адресом по стабильному ключу (osm_type, osm_id)."""

    osm_type: str = Field(min_length=1, max_length=16)
    osm_id: int
    reason: str = Field(default="", max_length=500)


class GeoFeatureSuppressRequest(StrictBaseModel):
    """Тумбстоун на объект слоя: barrier/signal/restriction/edge."""

    entity: Literal["barrier", "signal", "restriction", "edge"]
    osm_id: int
    reason: str = Field(default="", max_length=500)


class GeoEdgeCloseRequest(StrictBaseModel):
    """Закрытие режимов движения на всех рёбрах OSM way."""

    osm_way_id: int
    modes: list[RouteMode] = Field(min_length=1)
    reason: str = Field(default="", max_length=500)


class GeoEdgeTargetRequest(StrictBaseModel):
    """Операция над дорогой по osm_way_id."""

    osm_way_id: int


class GeoOverrideItem(StrictBaseModel):
    """Строка аудита правок: патч адреса, тумбстоун или закрытие дороги."""

    kind: str
    entity: str
    osm_type: str
    osm_id: int
    reason: str
    updated_by: str
    updated_at: str
    suppressed: bool = False


class GeoOverrideListResponse(StrictBaseModel):
    """Сводный аудит правок админа по всем сущностям."""

    items: list[GeoOverrideItem]
    total: int


class GeoOverridesListRequest(StrictBaseModel):
    """Страница аудита правок."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

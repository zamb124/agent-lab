"""Конфигурация Geo Service.

URL БД — `database.geo_url`, адреса соседей — `server.*_service_url`.
Источник и профили импорта задаются здесь: экстракты OSM, граница покрытия,
скорости по классам дорог и лимиты запросов.
"""

from pydantic import Field

from core.config import BaseSettings


class GeoSettings(BaseSettings):
    """Настройки гео-сервиса платформы."""

    osm_extract_urls: list[str] = Field(
        default_factory=lambda: [
            "https://download.bbbike.org/osm/bbbike/Moscow/Moscow.osm.pbf",
        ],
        description="PBF-экстракты OSM для импорта (объединение). Импорт потоковый — память не зависит от размера; BBBike Moscow (85MB) выбран как компактный источник города: Geofabrik central-fed-district (884MB) дольше качается и парсится, у download.openstreetmap.fr России нет.",
    )
    coverage_bbox: tuple[float, float, float, float] = Field(
        default=(54.2, 35.1, 56.9, 40.4),
        description="BBox покрытия (lat_min, lng_min, lat_max, lng_max): Москва и Московская область. Сидит дефолтный geo_regions.",
    )
    default_region_name: str = Field(
        default="moscow",
        description="Slug дефолтного региона, сидящегося из coverage_bbox/osm_extract_urls при пустом geo_regions.",
    )
    default_region_title: str = Field(
        default="Москва и Московская область",
        description="Название дефолтного региона покрытия.",
    )
    import_batch_size: int = Field(
        default=5000,
        ge=100,
        description="Размер пачки INSERT при импорте.",
    )
    car_speeds: dict[str, int] = Field(
        default_factory=lambda: {
            "motorway": 90,
            "trunk": 80,
            "primary": 60,
            "secondary": 50,
            "tertiary": 40,
            "unclassified": 30,
            "residential": 25,
            "living_street": 15,
            "service": 15,
            "road": 25,
            "track": 15,
        },
        description="Скорость car-профиля (км/ч) по классу highway. Классы вне словаря для car непроходимы.",
    )
    foot_speed_kmh: float = Field(
        default=4.5,
        gt=0,
        description="Скорость пешехода (км/ч) по всем ходовым классам.",
    )
    foot_speed_overrides: dict[str, float] = Field(
        default_factory=lambda: {"steps": 3.0, "path": 4.0, "track": 4.2, "bridleway": 4.0},
        description="Точечная скорость foot (км/ч) для классов, где базовая завышена.",
    )
    bike_speeds: dict[str, int] = Field(
        default_factory=lambda: {
            "trunk": 15,
            "primary": 16,
            "secondary": 17,
            "tertiary": 18,
            "unclassified": 18,
            "residential": 18,
            "living_street": 12,
            "service": 16,
            "road": 17,
            "cycleway": 20,
            "track": 13,
            "path": 11,
            "bridleway": 10,
            "pedestrian": 8,
            "footway": 8,
            "steps": 4,
        },
        description=(
            "Скорость bike-профиля (км/ч) по классу highway. Bike гибридный: "
            "едет и по проезжей части (кроме motor-классов без bicycle=yes), и по "
            "path/footway/pedestrian/steps — dijkstra выбирает самое быстрое."
        ),
    )
    scooter_speeds: dict[str, int] = Field(
        default_factory=lambda: {
            "trunk": 17,
            "primary": 18,
            "secondary": 19,
            "tertiary": 20,
            "unclassified": 20,
            "residential": 20,
            "living_street": 14,
            "service": 18,
            "road": 19,
            "cycleway": 22,
            "track": 14,
            "path": 12,
            "bridleway": 10,
            "pedestrian": 8,
            "footway": 8,
            "steps": 4,
        },
        description=(
            "Скорость scooter-профиля (км/ч, электросамокат) по классу highway. "
            "Те же правила доступа, что bike; чуть быстрее на дорогах."
        ),
    )
    light_road_fallback_kmh: dict[str, int] = Field(
        default_factory=lambda: {"bike": 16, "scooter": 18},
        description="Скорость bike/scooter на неизвестном дорожном классе (км/ч).",
    )
    light_path_fallback_kmh: dict[str, int] = Field(
        default_factory=lambda: {"bike": 9, "scooter": 9},
        description="Скорость bike/scooter на неизвестном пешем классе (км/ч).",
    )
    signal_delay_s: dict[str, float] = Field(
        default_factory=lambda: {
            "car": 15.0,
            "bike": 8.0,
            "scooter": 8.0,
            "foot": 0.0,
        },
        description=(
            "Штраф (сек) за транзит через вершину highway=traffic_signals "
            "по режиму — среднее ожидание зелёного. Пешеходных сигналов на "
            "проезжей части у узла нет: foot-штраф 0."
        ),
    )
    matrix_max_cells: int = Field(
        default=10_000,
        ge=1,
        description="Максимум ячеек sources×targets в route/matrix.",
    )
    tsp_max_points: int = Field(
        default=25,
        ge=2,
        description="Максимум точек в route/optimal_order (плюс старт).",
    )
    isochrone_max_minutes: int = Field(
        default=120,
        ge=1,
        description="Максимальная дальность изохроны (минуты).",
    )
    snap_max_distance_m: int = Field(
        default=3000,
        ge=1,
        description="Максимальная дистанция притяжки точки к графу (метры).",
    )
    suggest_limit_max: int = Field(
        default=20,
        ge=1,
        description="Максимальный limit в addresses/suggest.",
    )
    zone_addresses_limit_max: int = Field(
        default=500,
        ge=1,
        description="Максимальный limit страницы в addresses/in_zone.",
    )
    osm_http_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Таймаут HEAD-запросов к экстрактам; download идёт потоком без общего read-timeout.",
    )
    sync_enabled: bool = Field(
        default=True,
        description="Разрешить фактический импорт в geo_osm_sync_tick (False — тик завершается no-op).",
    )
    tiles_dir: str = Field(
        default="data/tiles",
        description=(
            "Директория векторной базовой карты: basemap.pmtiles + "
            "fonts/{Fontstack}/{range}.pbf + sprites/{flavor}.*. Наполняется "
            "geo_tiles_sync или scripts/geo/fetch_basemap.py."
        ),
    )
    tiles_pmtiles_source: str = Field(
        default="https://build.protomaps.com/20251027.pmtiles",
        description=(
            "Источник planet.pmtiles (Protomaps daily build, pinned датой) для "
            "geo_tiles_sync — extract режется по coverage_bbox."
        ),
    )
    tiles_pmtiles_bin: str = Field(
        default="pmtiles",
        description="Путь к pmtiles CLI (extract) для geo_tiles_sync.",
    )
    tiles_assets_url: str = Field(
        default="https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.tar.gz",
        description=(
            "Tarball с glyphs-шрифтами и sprites стилей (protomaps/basemaps-assets) "
            "для geo_tiles_sync."
        ),
    )
    tiles_cache_seconds: int = Field(
        default=86400,
        ge=0,
        description="Cache-Control max-age для /tiles/* (ассеты версионируются синком).",
    )

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
            "https://download.openstreetmap.fr/extracts/europe/russia/central_federal_district/moscow.osm.pbf",
            "https://download.openstreetmap.fr/extracts/europe/russia/central_federal_district/moscow_oblast.osm.pbf",
        ],
        description="PBF-экстракты OSM для импорта (объединение). Альтернатива — Geofabrik central-fed-district.",
    )
    coverage_bbox: tuple[float, float, float, float] = Field(
        default=(54.2, 35.1, 56.9, 40.4),
        description="BBox покрытия (lat_min, lng_min, lat_max, lng_max): Москва и Московская область.",
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

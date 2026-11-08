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
    enrich_tick_batch: int = Field(
        default=100,
        ge=1,
        description="Размер пачки задач обогащения за один geo_enrich_tick.",
    )
    enrich_max_attempts: int = Field(
        default=5,
        ge=1,
        description="Попыток задачи обогащения до failed.",
    )
    enrich_retry_pause_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Базовая пауза retry обогащения (сек); умножается на номер попытки.",
    )
    gar_sync_enabled: bool = Field(
        default=True,
        description="Разрешить синк ГАР/ФИАС в geo_gar_sync (False — тик завершается no-op).",
    )
    gar_info_url: str = Field(
        default="https://fias.nalog.ru/WebServices/Public",
        description=(
            "Endpoint DownloadService ФИАС: GetLastDownloadFileInfo и "
            "GetAllDownloadFileInfo отдают JSON с GarXMLFullURL/GarXMLDeltaURL."
        ),
    )
    gar_region_codes: dict[str, str] = Field(
        default_factory=lambda: {"moscow": "77"},
        description="Slug региона покрытия → код региона ГАР (директория внутри gar_xml.zip).",
    )
    gar_work_dir: str = Field(
        default="data/tiles/gar",
        description=(
            "Рабочая директория загрузок ГАР: zip с resume по HTTP Range + "
            "state_{region}.json (дельта-контекст). Дефолт ложится на общий PVC "
            "geo-tiles (/app/data/tiles) — персистентно в проде без отдельного тома."
        ),
    )
    gar_max_delta_chain: int = Field(
        default=30,
        ge=1,
        description="Максимум дельт подряд от курсора; цепочка длиннее или с разрывом → полная выгрузка.",
    )
    gar_match_similarity: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Порог схожести названия улицы при матче дома ГАР к адресу справочника.",
    )
    gar_http_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Таймаут запросов к DownloadService и HEAD архивов; download идёт потоком.",
    )
    gar_unresolved_defer_seconds: float = Field(
        default=86400.0,
        gt=0,
        description="Отсрочка повторного дрейна задачи gar_unresolved (сек) до появления резолвера.",
    )
    nspd_sync_enabled: bool = Field(
        default=True,
        description="Разрешить краул НСПД (False — тик завершается no-op).",
    )
    nspd_base_url: str = Field(
        default="https://nspd.gov.ru",
        description="Базовый URL публичного API НСПД (geoportal + aeggis).",
    )
    nspd_referer: str = Field(
        default="https://nspd.gov.ru/map?thematic=PKK",
        description="Referer запросов к НСПД: без него API отвечает 403.",
    )
    nspd_cell_deg: float = Field(
        default=0.02,
        gt=0,
        le=1.0,
        description="Сторона ячейки краула в градусах (~2 км): intersects-запрос на ячейку.",
    )
    nspd_tick_batch: int = Field(
        default=25,
        ge=1,
        description="Ячеек сетки региона за один тик GEO_NSPD_CRAWL.",
    )
    nspd_rps: float = Field(
        default=1.0,
        gt=0,
        le=10.0,
        description="Лимит запросов к НСПД в секунду: агрессивный краул банится по 403.",
    )
    nspd_building_layer_id: int = Field(
        default=36049,
        ge=1,
        description="layer_id/category_id слоя «Здания» НСПД для intersects и search.",
    )
    nspd_max_retries: int = Field(
        default=3,
        ge=1,
        description="Повторов запроса к НСПД при 403/429/5xx с backoff.",
    )
    nspd_retry_pause_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Базовая пауза retry НСПД (сек); умножается на номер попытки.",
    )
    nspd_http_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Таймаут запросов к API НСПД.",
    )
    nspd_unresolved_defer_seconds: float = Field(
        default=21600.0,
        gt=0,
        description="Отсрочка повторного дрейна gar_unresolved при неудачном резолве (сек).",
    )
    data_mos_sync_enabled: bool = Field(
        default=True,
        description="Разрешить синк data.mos.ru (False — тик завершается no-op).",
    )
    data_mos_base_url: str = Field(
        default="https://apidata.mos.ru",
        description="Базовый URL API Портала открытых данных Москвы.",
    )
    data_mos_api_key: str = Field(
        default="",
        description="API-ключ apidata.mos.ru; пустой — тик отвечает skipped=no_api_key.",
    )
    data_mos_datasets: dict[str, str] = Field(
        default_factory=lambda: {"60562": "address"},
        description="dataset_id → вид сущности ('address' — адресный реестр).",
    )
    data_mos_page_size: int = Field(
        default=500,
        ge=1,
        le=1000,
        description="Строк на страницу /v1/datasets/{id}/rows ($top).",
    )
    data_mos_tick_pages: int = Field(
        default=10,
        ge=1,
        description="Страниц датасета за один тик GEO_DATAMOS_SYNC (resume по курсору).",
    )
    data_mos_match_similarity: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Порог схожести улицы при матче строки датасета к адресу справочника.",
    )
    data_mos_http_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Таймаут запросов к apidata.mos.ru.",
    )
    overture_sync_enabled: bool = Field(
        default=True,
        description="Разрешить импорт Overture Maps (False — тик no-op).",
    )
    overture_base_url: str = Field(
        default="https://overturemapswestus2.blob.core.windows.net/release",
        description=(
            "Корень релизов Overture: Azure-mirror container либо "
            "file:// каталог с зеркалом раскладки {release}/theme=…/type=…/."
        ),
    )
    overture_release: str = Field(
        default="2025-11-19.0",
        description="Версия релиза Overture Maps (первая часть пути parquet).",
    )
    overture_themes: list[str] = Field(
        default_factory=lambda: ["addresses", "buildings"],
        description="Темы релиза к импорту: addresses → gen-0 gap-fill, buildings → geo_buildings.",
    )
    overture_tick_rowgroups: int = Field(
        default=10,
        ge=1,
        description="Parquet row-groups за один тик GEO_OVERTURE_SYNC (resume по курсору).",
    )
    overture_gap_radius_m: float = Field(
        default=25.0,
        gt=0,
        description="Радиус gap-fill дедупа (м): адрес Overture пропускается, если рядом тот же housenumber.",
    )
    overture_http_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        description="Таймаут чтения parquet/listing по HTTPS.",
    )
    osm_diff_tick_enabled: bool = Field(
        default=True,
        description=(
            "Тик свежести по replication state.txt: удалённая последовательность "
            "новее курсора → enqueue полного GEO_OSM_SYNC_TICK."
        ),
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

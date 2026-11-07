"""Declaration-модуль geo задач (очередь ``geo``).

Лёгкий: только объявления. Импортируется producer'ами (``enqueue``)
и impl-модулями (``@platform_task``).
"""

from core.tasks import declare_task

GEO_OSM_SYNC_TICK = declare_task(
    "geo_osm_sync_tick", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_TILES_SYNC = declare_task(
    "geo_tiles_sync", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_ENRICH_TICK = declare_task(
    "geo_enrich_tick", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_GAR_SYNC = declare_task(
    "geo_gar_sync", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_NSPD_CRAWL = declare_task(
    "geo_nspd_crawl", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_DATAMOS_SYNC = declare_task(
    "geo_datamos_sync", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_OVERTURE_SYNC = declare_task(
    "geo_overture_sync", queue="geo", scheduled=True, retry=True, max_retries=1
)

GEO_OSM_DIFF_TICK = declare_task(
    "geo_osm_diff_tick", queue="geo", scheduled=True, retry=True, max_retries=1
)

__all__ = [
    "GEO_DATAMOS_SYNC",
    "GEO_ENRICH_TICK",
    "GEO_GAR_SYNC",
    "GEO_NSPD_CRAWL",
    "GEO_OSM_DIFF_TICK",
    "GEO_OSM_SYNC_TICK",
    "GEO_OVERTURE_SYNC",
    "GEO_TILES_SYNC",
]

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

__all__ = ["GEO_OSM_SYNC_TICK", "GEO_TILES_SYNC"]

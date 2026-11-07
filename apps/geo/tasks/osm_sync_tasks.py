"""Scheduled-синхронизация OSM-данных справочника и графа."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_OSM_SYNC_TICK)
async def geo_osm_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, SqlParameterValue]:
    """If-Modified-Since → импорт → своп поколения (см. OsmImportService)."""
    _ = (schedule_task_id, company_id)
    return await di.osm_import_service.run_sync()

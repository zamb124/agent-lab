"""Scheduled-тик свежести OSM по replication state Geofabrik."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_OSM_DIFF_TICK
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_OSM_DIFF_TICK)
async def geo_osm_diff_tick(di: Di) -> dict[str, SqlParameterValue]:
    """Replication state.txt → enqueue полного синка при устаревании
    (см. OsmDiffService.run_tick)."""
    result = await di.osm_diff_service.run_tick()
    return result.model_dump()

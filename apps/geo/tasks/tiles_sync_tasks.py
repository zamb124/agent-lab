"""Provision векторной базовой карты: PMTiles-extract + fonts/sprites."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_TILES_SYNC
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_TILES_SYNC)
async def geo_tiles_sync(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, SqlParameterValue]:
    """См. ``GeoTilesService.sync``."""
    _ = (schedule_task_id, company_id)
    return await di.geo_tiles_service.sync()

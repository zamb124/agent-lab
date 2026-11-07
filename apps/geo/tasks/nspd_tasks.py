"""Scheduled-краул НСПД/ЕГРН: сетка ячеек → здания → кадастровые линки."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_NSPD_CRAWL
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_NSPD_CRAWL)
async def geo_nspd_crawl(di: Di) -> dict[str, SqlParameterValue]:
    """НСПД intersects-сетка по регионам → ``geo_buildings`` + cadastral
    (см. NspdCrawlService.run_crawl)."""
    result = await di.nspd_crawl_service.run_crawl()
    return result.model_dump()

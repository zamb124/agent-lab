"""Scheduled-синк датасетов Портала открытых данных Москвы."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_DATAMOS_SYNC
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_DATAMOS_SYNC)
async def geo_datamos_sync(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, SqlParameterValue]:
    """Страницы датасетов apidata.mos.ru → enrich-матч адресов
    (см. DataMosImportService.run_sync)."""
    _ = (schedule_task_id, company_id)
    result = await di.datamos_import_service.run_sync()
    return result.model_dump()

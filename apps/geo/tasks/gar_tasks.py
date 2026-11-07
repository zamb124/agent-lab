"""Scheduled-синхронизация ГАР/ФИАС: версии → дельты/полная → enrich."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_GAR_SYNC
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_GAR_SYNC)
async def geo_gar_sync(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, SqlParameterValue]:
    """DownloadService ФИАС → дельта-цепочка или полная выгрузка
    (см. GarImportService.run_sync)."""
    _ = (schedule_task_id, company_id)
    result = await di.gar_import_service.run_sync()
    return result.model_dump()

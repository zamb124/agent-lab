"""Месячный импорт релиза Overture Maps (parquet, gap-fill + здания)."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_OVERTURE_SYNC
from core.tasks import platform_task
from core.types import SqlParameterValue


@platform_task(GEO_OVERTURE_SYNC)
async def geo_overture_sync(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, SqlParameterValue]:
    """Row-groups релиза Overture → gen-0 адреса и ``geo_buildings``
    (см. OvertureImportService.run_sync)."""
    _ = (schedule_task_id, company_id)
    result = await di.overture_import_service.run_sync()
    return result.model_dump()

"""Тик дрейна очереди фонового обогащения геоданных."""

from apps.geo.di import Di
from apps.geo.tasks.task_names import GEO_ENRICH_TICK
from core.tasks import platform_task


@platform_task(GEO_ENRICH_TICK)
async def geo_enrich_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, int]:
    """Пачка pending-задач обогащения по kind-реестру (см. GeoEnrichService)."""
    _ = (schedule_task_id, company_id)
    return await di.geo_enrich_service.drain()

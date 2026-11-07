"""Тик свежести OSM по replication-диффам Geofabrik.

``GeoRegion.replication_url`` — osmosis replication root
(``https://download.geofabrik.de/<area>-updates``). ``ReplicationServer``
читает ``state.txt`` (последняя ``sequenceNumber``); курсор
``geo_source_cursors(source='osm_diff', region)`` — последняя
увиденная последовательность.

v1 — observer + enqueue, НЕ инкрементальный apply: удалённая
последовательность новее курсора → опубликованный экстракт устарел →
``enqueue(GEO_OSM_SYNC_TICK)`` — полный ре-импорт идёт по доказанному
атомарному пути (staging-поколение → своп), живое поколение никогда не
мутирует. Реальный apply ``.osc.gz`` в живое поколение требует
pgrouting-aware инкрементального движка (пересчёт source/target рёбер,
вершин, ограничений по затронутым way) — следующий шаг фазы; пока
свежесть данных обеспечивается честным полным ре-синком.

Lock не нужен: сам тик только читает state и ставит задачу; конкурентные
полные импорты сериализует ``geo_import_lock`` внутри ``run_sync``.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import osmium.replication.server
from pydantic import BaseModel

from apps.geo.config import GeoSettings
from apps.geo.models.geo_region import GeoRegion
from apps.geo.models.geo_source import GeoSource
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.imports import module_sdk
from core.logging import get_logger
from core.tasks import enqueue
from core.types import JsonObject

_SOURCE = "osm_diff"

_logger = get_logger(__name__)


class _ReplicationState(Protocol):
    sequence: int


class _ReplicationServer(Protocol):
    def get_state_info(self, seq: int | None = None) -> _ReplicationState | None: ...


class _ReplicationModule(Protocol):
    def ReplicationServer(self, base_url: str) -> _ReplicationServer: ...  # noqa: N802 — имя пакета


_REPL = module_sdk(osmium.replication.server, _ReplicationModule)


class OsmDiffResult(BaseModel):
    """Итог тика: ``skipped`` — причина пропуска, иначе по регионам."""

    skipped: str = ""
    regions: dict[str, JsonObject] = {}
    enqueued: bool = False


class OsmDiffService:
    """Observer replication-state → enqueue полного OSM-синка при устаревании."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def run_tick(self) -> OsmDiffResult:
        """Регионы с ``replication_url`` → state.txt → курсор → enqueue."""
        if not self._settings.osm_diff_tick_enabled:
            return OsmDiffResult(skipped="osm_diff_tick_disabled")
        source = await GeoSource.by_name("geofabrik")
        if source is not None and not source.enabled:
            return OsmDiffResult(skipped="source_disabled")
        regions = [
            region
            for region in await GeoRegion.list_enabled_by_name_asc()
            if region.replication_url
        ]
        if not regions:
            return OsmDiffResult(skipped="no_regions")
        regions_result: dict[str, JsonObject] = {}
        enqueued = False
        for region in regions:
            try:
                regions_result[region.name], did = await self._check_region(
                    region
                )
                enqueued = enqueued or did
            except Exception as exc:
                await GeoSourceCursor.mark_failed(
                    source=_SOURCE,
                    region=region.name,
                    error=f"{type(exc).__name__}: {exc}",
                )
                regions_result[region.name] = {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        return OsmDiffResult(regions=regions_result, enqueued=enqueued)

    async def _check_region(self, region: GeoRegion) -> tuple[JsonObject, bool]:
        """state.txt → ``(результат, поставлен ли синк)``."""
        server = _REPL.ReplicationServer(region.replication_url)
        info = await asyncio.to_thread(server.get_state_info)
        if info is None:
            raise ValueError("replication state.txt unavailable")
        remote = int(info.sequence)
        cursor = await GeoSourceCursor.by_source_region(_SOURCE, region.name)
        if cursor is None:
            _ = await GeoSourceCursor.upsert_progress(
                source=_SOURCE,
                region=region.name,
                cursor=str(remote),
                rows_done=0,
                status=GeoCursorStatus.DONE,
            )
            return {"status": "baselined", "sequence": remote}, False
        try:
            local = int(cursor.cursor)
        except ValueError:
            local = 0
        if remote <= local:
            return {"status": "current", "sequence": remote}, False
        _ = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
        _ = await GeoSourceCursor.upsert_progress(
            source=_SOURCE,
            region=region.name,
            cursor=str(remote),
            rows_done=0,
            status=GeoCursorStatus.DONE,
        )
        return {"status": "sync_enqueued", "sequence": remote}, True

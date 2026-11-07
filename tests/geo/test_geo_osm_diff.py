"""Geo: тик свежести OSM — replication state.txt → enqueue полного синка.

Реальный wire-путь: эмулятор osmosis replication на :18104 (формат
state.txt Geofabrik), реальный Postgres, реальный TaskIQ-брокер —
постановка ``geo_osm_sync_tick`` проверяется записью в stream ``geo``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import redis.asyncio as aioredis
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_region import GeoRegion, GeoRegionKind
from apps.geo.models.geo_source import GeoSource, GeoSourceKind
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.services.osm_diff_service import OsmDiffService
from apps.geo.tasks import task_names  # noqa: F401 — регистрирует Spec'ы

_REGION = "moscow"
_EMULATOR = "http://127.0.0.1:18104/geofabrik-updates/"
_BROKER = "redis://localhost:63792/1"

pytestmark = pytest.mark.xdist_group("geo")


@pytest.fixture(autouse=True)
async def _clean():
    """Регион, курсор и реестр geofabrik — чисты."""
    _ = await execute_raw(
        "DELETE FROM geo_source_cursors WHERE source = 'osm_diff'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_sources WHERE name = 'geofabrik'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_regions WHERE name = $1", [_REGION], using="geo"
    )


@pytest.fixture
async def _region() -> None:
    """Регион moscow — delete+create: одноимённые регионы других файлов сьюта."""
    _ = await execute_raw(
        "DELETE FROM geo_regions WHERE name = $1", [_REGION], using="geo"
    )
    now = datetime.now(UTC)
    _ = await GeoRegion.objects.create(
        instance=GeoRegion(
            name=_REGION,
            title="Diff e2e",
            kind=GeoRegionKind.CITY,
            bbox_south=55.3,
            bbox_west=37.3,
            bbox_north=56.0,
            bbox_east=37.9,
            replication_url=_EMULATOR,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture
def service() -> OsmDiffService:
    return OsmDiffService(GeoSettings())


async def _stream_has_task(name: str, after_id: bytes) -> bool:
    """Stream ``geo`` содержит задачу ``name`` позже ``after_id``."""
    client = aioredis.from_url(_BROKER)
    try:
        entries = await client.xrange("geo", min=after_id, max="+")
        for _entry_id, fields in entries:
            payload = b"".join(fields.values())
            if name.encode() in payload:
                return True
        return False
    finally:
        await client.aclose()


async def test_diff_stale_region_enqueues_full_sync(
    service: OsmDiffService, _region: None
) -> None:
    _ = await GeoSourceCursor.upsert_progress(
        source="osm_diff",
        region=_REGION,
        cursor="4999",
        rows_done=0,
        status=GeoCursorStatus.DONE,
    )
    client = aioredis.from_url(_BROKER)
    try:
        tail = await client.xrevrange("geo", count=1)
        after = tail[0][0] if tail else b"0-0"
    finally:
        await client.aclose()
    result = await service.run_tick()
    assert result.enqueued is True
    region = result.regions[_REGION]
    assert region["status"] == "sync_enqueued"
    assert region["sequence"] == 5000
    cursor = await GeoSourceCursor.by_source_region("osm_diff", _REGION)
    assert cursor is not None
    assert cursor.cursor == "5000"
    # Wire-путь: задача полного синка реально записана в stream брокера.
    assert await _stream_has_task("geo_osm_sync_tick", after)


async def test_diff_current_region_noop(
    service: OsmDiffService, _region: None
) -> None:
    _ = await GeoSourceCursor.upsert_progress(
        source="osm_diff",
        region=_REGION,
        cursor="5000",
        rows_done=0,
        status=GeoCursorStatus.DONE,
    )
    result = await service.run_tick()
    assert result.enqueued is False
    assert result.regions[_REGION]["status"] == "current"


async def test_diff_first_run_baselines(
    service: OsmDiffService, _region: None
) -> None:
    result = await service.run_tick()
    assert result.enqueued is False
    assert result.regions[_REGION]["status"] == "baselined"
    cursor = await GeoSourceCursor.by_source_region("osm_diff", _REGION)
    assert cursor is not None
    assert cursor.cursor == "5000"


async def test_diff_source_disabled_skips(service: OsmDiffService) -> None:
    now = datetime.now(UTC)
    _ = await GeoSource.objects.create(
        instance=GeoSource(
            name="geofabrik",
            title="Geofabrik",
            kind=GeoSourceKind.EXTRACT,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
    )
    result = await service.run_tick()
    assert result.skipped == "source_disabled"


async def test_diff_tick_disabled_skips() -> None:
    service = OsmDiffService(GeoSettings(osm_diff_tick_enabled=False))
    result = await service.run_tick()
    assert result.skipped == "osm_diff_tick_disabled"

"""Geo: импортёр ГАР/ФИАС — версии, дельта-цепочка, состояние, матч.

Реальный wire-путь: эмулятор DownloadService ФИАС на :18101 (стек),
реальный Postgres. Полная выгрузка → дельта-цепочка со state-merge →
деактивация дома → full-fallback при разрыве/потере состояния.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_enrich_item import GeoEnrichItem, GeoEnrichStatus
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_source import GeoSource, GeoSourceKind
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.services.gar_import_service import GarImportService

_EMULATOR = "http://127.0.0.1:18101/WebServices/Public"
_GEN = 990_000_010
_REGION = "moscow"

pytestmark = pytest.mark.xdist_group("geo")


@pytest.fixture(autouse=True)
def _test_generation(monkeypatch: pytest.MonkeyPatch):
    """Сервисы читают тестовое поколение, глобальная строка не трогается."""

    async def _gen(cls) -> int:  # noqa: ANN001 — сигнатуру диктует classmethod
        return _GEN

    monkeypatch.setattr(GeoImportState, "active_generation", classmethod(_gen))


@pytest.fixture(autouse=True)
async def _clean():
    """Адреса-фикстуры, enrich, очередь, курсор и реестр gar — чисты."""
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE generation = $1 AND osm_id >= 9100",
        [_GEN],
        using="geo",
    )
    _ = await execute_raw("DELETE FROM geo_address_enrich", using="geo")
    _ = await execute_raw(
        "DELETE FROM geo_enrich_queue WHERE kind = 'gar_unresolved'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_source_cursors WHERE source = 'gar'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_stats WHERE source = 'gar'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_sources WHERE name = 'gar'", using="geo"
    )


@pytest.fixture
def settings(tmp_path: Path) -> GeoSettings:
    return GeoSettings(
        gar_info_url=_EMULATOR,
        gar_work_dir=str(tmp_path),
        gar_region_codes={_REGION: "77"},
    )


@pytest.fixture
def service(settings: GeoSettings) -> GarImportService:
    return GarImportService(settings)


@pytest.fixture
async def _seed_addresses() -> None:
    """Пять домов Москвы тестового поколения — кандидаты матча."""
    rows = [
        (9101, "Тверская улица, 1", "Тверская улица", "1"),
        (9102, "Тверская улица, 3", "Тверская улица", "3"),
        (9103, "Никольская улица, 10", "Никольская улица", "10"),
        (9104, "Арбат, 5", "Арбат", "5"),
        (9105, "Большая Садовая улица, 7", "Большая Садовая улица", "7"),
    ]
    now = datetime.now(UTC)
    for osm_id, display, street, housenum in rows:
        _ = await execute_raw(
            """
            INSERT INTO geo_addresses
                (osm_type, osm_id, display_name, city, street, housenumber,
                 postcode, lat, lng, region, generation, source, gar_guid,
                 canonical_name, cadastral_number, created_at)
            VALUES ('node', $1, $2, 'Москва', $3, $4,
                    '', 55.76, 37.61, $5, $6, 'osm', '', '', '', $7)
            """,
            [osm_id, display, street, housenum, _REGION, _GEN, now],
            using="geo",
        )


async def test_gar_full_sync_matches_and_enqueues_unresolved(
    service: GarImportService, _seed_addresses: None
) -> None:
    result = await service.run_sync()
    region = result.regions[_REGION]
    assert region.status == "done"
    assert region.mode == "full"
    assert region.matched == 4
    assert region.unresolved == 1
    enrich = await GeoAddressEnrich.by_object(osm_type="node", osm_id=9101)
    assert enrich is not None
    assert enrich.gar_guid == "11111111-1111-1111-1111-111111111101"
    assert enrich.canonical_name == "г. Москва, ул. Тверская, д. 1"
    live = await execute_raw(
        "SELECT gar_guid, canonical_name FROM geo_addresses WHERE osm_id = 9101",
        using="geo",
    )
    assert live[0]["gar_guid"] == "11111111-1111-1111-1111-111111111101"
    queued = await GeoEnrichItem.objects.filter(
        kind="gar_unresolved", status=GeoEnrichStatus.PENDING
    ).all()
    assert len(queued) == 1
    assert queued[0].payload["gar_objectid"] == "105"
    cursor = await GeoSourceCursor.by_source_region("gar", _REGION)
    assert cursor is not None
    assert cursor.status == GeoCursorStatus.DONE
    assert cursor.cursor == "100"


async def test_gar_second_run_is_noop(
    service: GarImportService, _seed_addresses: None
) -> None:
    _ = await service.run_sync()
    result = await service.run_sync()
    assert result.regions[_REGION].status == "current"


async def test_gar_delta_chain_merges_state_and_deactivates(
    service: GarImportService, _seed_addresses: None
) -> None:
    _ = await service.run_sync()
    _ = await GeoSourceCursor.upsert_progress(
        source="gar", region=_REGION, cursor="97", rows_done=0,
        status=GeoCursorStatus.DONE,
    )
    result = await service.run_sync()
    region = result.regions[_REGION]
    assert region.mode == "delta"
    assert region.versions == 3
    # v98: дома 101+106, v99: 102, v100: 103+104 (105 — промах, 106 — gone).
    assert region.matched == 5
    assert region.unresolved == 1
    gone_enrich = await GeoAddressEnrich.by_object(osm_type="node", osm_id=9105)
    assert gone_enrich is None
    live = await execute_raw(
        "SELECT gar_guid FROM geo_addresses WHERE osm_id = 9105", using="geo"
    )
    assert live[0]["gar_guid"] == ""
    cursor = await GeoSourceCursor.by_source_region("gar", _REGION)
    assert cursor is not None
    assert cursor.cursor == "100"


async def test_gar_stateless_cursor_falls_back_to_full(
    service: GarImportService, settings: GeoSettings, _seed_addresses: None
) -> None:
    _ = await GeoSourceCursor.upsert_progress(
        source="gar", region=_REGION, cursor="97", rows_done=0,
        status=GeoCursorStatus.DONE,
    )
    assert not (Path(settings.gar_work_dir) / f"state_{_REGION}.json").exists()
    result = await service.run_sync()
    assert result.regions[_REGION].mode == "full"


async def test_gar_broken_delta_chain_falls_back_to_full(
    tmp_path: Path, _seed_addresses: None
) -> None:
    settings = GeoSettings(
        gar_info_url=_EMULATOR,
        gar_work_dir=str(tmp_path),
        gar_region_codes={_REGION: "77"},
        gar_max_delta_chain=1,
    )
    service = GarImportService(settings)
    _ = await GeoSourceCursor.upsert_progress(
        source="gar", region=_REGION, cursor="97", rows_done=0,
        status=GeoCursorStatus.DONE,
    )
    result = await service.run_sync()
    assert result.regions[_REGION].mode == "full"


async def test_gar_source_disabled_skips(service: GarImportService) -> None:
    now = datetime.now(UTC)
    _ = await GeoSource.objects.create(
        instance=GeoSource(
            name="gar",
            title="ГАР",
            kind=GeoSourceKind.REGISTRY,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
    )
    result = await service.run_sync()
    assert result.skipped == "source_disabled"

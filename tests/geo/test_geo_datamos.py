"""Geo: импортёр data.mos.ru — пагинация, resume-курсор, матч адресов.

Реальный wire-путь: эмулятор apidata.mos.ru на :18103 (стек), реальный
Postgres. Датасет режется страницами ``$top``/$skip — тик добирает
``data_mos_tick_pages`` и продолжает с курсора; строки ``address`` матчатся
к ``geo_addresses`` и пишут ``canonical_name`` в ``geo_address_enrich``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion, GeoRegionKind
from apps.geo.models.geo_source import GeoSource, GeoSourceKind
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services.datamos_import_service import DataMosImportService

_EMULATOR = "http://127.0.0.1:18103"
_GEN = 990_000_020
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
    """Адреса-фикстуры, enrich, курсор и реестр data_mos_ru — чисты."""
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE generation = $1 AND osm_id >= 9200",
        [_GEN],
        using="geo",
    )
    _ = await execute_raw("DELETE FROM geo_address_enrich", using="geo")
    _ = await execute_raw(
        "DELETE FROM geo_source_cursors WHERE source = 'data_mos_ru'",
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_stats WHERE source = 'data_mos_ru'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_sources WHERE name = 'data_mos_ru'", using="geo"
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
            title="data.mos.ru e2e",
            kind=GeoRegionKind.CITY,
            bbox_south=55.3,
            bbox_west=37.3,
            bbox_north=56.0,
            bbox_east=37.9,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture
def settings() -> GeoSettings:
    return GeoSettings(
        data_mos_base_url=_EMULATOR,
        data_mos_api_key="test-datamos-key",
        data_mos_page_size=2,
        data_mos_tick_pages=2,
        data_mos_datasets={"60562": "address"},
    )


@pytest.fixture
def service(settings: GeoSettings) -> DataMosImportService:
    return DataMosImportService(settings)


@pytest.fixture
async def _seed_addresses() -> None:
    """Пять домов Москвы тестового поколения — кандидаты матча."""
    rows = [
        (9201, "Тверская улица, 1", "Тверская улица", "1"),
        (9202, "Тверская улица, 3", "Тверская улица", "3"),
        (9203, "Никольская улица, 10", "Никольская улица", "10"),
        (9204, "Арбат, 5", "Арбат", "5"),
        (9205, "Большая Садовая улица, 7", "Большая Садовая улица", "7"),
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


async def test_datamos_sync_pages_resume_and_match(
    service: DataMosImportService, _region: None, _seed_addresses: None
) -> None:
    # Тик 1: page_size=2, tick_pages=2 → 4 строки, курсор «4» RUNNING.
    first = await service.run_sync()
    cursor_key = f"{_REGION}:60562"
    assert first.datasets[cursor_key]["rows"] == 4
    cursor = await GeoSourceCursor.by_source_region("data_mos_ru", cursor_key)
    assert cursor is not None
    assert cursor.status == GeoCursorStatus.RUNNING
    assert cursor.cursor == "4"
    # Тик 2: хвост (1 строка < page_size) → DONE; «пл. Революции» — промах.
    second = await service.run_sync()
    assert second.datasets[cursor_key]["status"] == "done"
    assert second.datasets[cursor_key]["matched"] == 0
    enrich = await GeoAddressEnrich.by_object(osm_type="node", osm_id=9201)
    assert enrich is not None
    assert enrich.canonical_name == "г. Москва, ул. Тверская, д. 1"
    arb = await GeoAddressEnrich.by_object(osm_type="node", osm_id=9204)
    assert arb is not None
    cursor = await GeoSourceCursor.by_source_region("data_mos_ru", cursor_key)
    assert cursor is not None
    assert cursor.status == GeoCursorStatus.DONE
    assert cursor.cursor == "5"


async def test_datamos_full_pass_matched_count_and_stats(
    _region: None, _seed_addresses: None,
) -> None:
    service = DataMosImportService(
        GeoSettings(
            data_mos_base_url=_EMULATOR,
            data_mos_api_key="test-datamos-key",
            data_mos_page_size=10,
            data_mos_tick_pages=10,
            data_mos_datasets={"60562": "address"},
        )
    )
    result = await service.run_sync()
    dataset = result.datasets[f"{_REGION}:60562"]
    assert dataset["status"] == "done"
    assert dataset["rows"] == 5
    assert dataset["matched"] == 4
    stats = await GeoStats.objects.filter(
        source="data_mos_ru", region=_REGION, entity="dataset_address"
    ).all()
    assert stats[0].rows == 4


async def test_datamos_done_cursor_is_current(
    _region: None, _seed_addresses: None,
) -> None:
    service = DataMosImportService(
        GeoSettings(
            data_mos_base_url=_EMULATOR,
            data_mos_api_key="test-datamos-key",
            data_mos_datasets={"60562": "address"},
        )
    )
    _ = await service.run_sync()
    second = await service.run_sync()
    assert second.datasets[f"{_REGION}:60562"]["status"] == "current"


async def test_datamos_no_api_key_skips(_region: None) -> None:
    service = DataMosImportService(
        GeoSettings(data_mos_base_url=_EMULATOR, data_mos_api_key="")
    )
    result = await service.run_sync()
    assert result.skipped == "no_api_key"


async def test_datamos_source_disabled_skips(
    service: DataMosImportService,
) -> None:
    now = datetime.now(UTC)
    _ = await GeoSource.objects.create(
        instance=GeoSource(
            name="data_mos_ru",
            title="data.mos.ru",
            kind=GeoSourceKind.API,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
    )
    result = await service.run_sync()
    assert result.skipped == "source_disabled"


async def test_datamos_sync_disabled_skips() -> None:
    service = DataMosImportService(
        GeoSettings(data_mos_sync_enabled=False, data_mos_api_key="k")
    )
    result = await service.run_sync()
    assert result.skipped == "data_mos_sync_disabled"

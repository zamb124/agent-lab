"""Geo: краулер НСПД — сетка ячеек, здания, кадастровые линки, резолв ГАР.

Реальный wire-путь: эмулятор geoportal/aeggis НСПД на :18102 (стек),
реальный Postgres/PostGIS. Тик краулит сетку bbox региона по ячейкам
(cursor=cell_index, resume), здания идут в ``geo_buildings``, точки
адресов внутри контуров получают ``cadastral_number`` в enrich и живых
колонках; ``gar_unresolved`` резолвится поиском в gen-0 адрес
``source='gar'``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_building import GeoBuilding
from apps.geo.models.geo_enrich_item import GeoEnrichItem, GeoEnrichStatus
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion, GeoRegionKind
from apps.geo.models.geo_source import GeoSource, GeoSourceKind
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.services.geo_enrich_service import GeoEnrichService
from apps.geo.services.nspd_crawl_service import NspdClient, NspdCrawlService
from core.http import get_httpx_client

_EMULATOR = "http://127.0.0.1:18102"
_GEN = 990_000_020
_REGION = "nspd_e2e"

pytestmark = pytest.mark.xdist_group("geo")


@pytest.fixture(autouse=True)
def _test_generation(monkeypatch: pytest.MonkeyPatch):
    """Сервисы читают тестовое поколение, глобальная строка не трогается."""

    async def _gen(cls) -> int:  # noqa: ANN001 — сигнатуру диктует classmethod
        return _GEN

    monkeypatch.setattr(GeoImportState, "active_generation", classmethod(_gen))


@pytest.fixture(autouse=True)
async def _clean() -> None:
    """Регион/здания/адреса/очередь/курсор/reестр nspd+gar — чисты."""
    _ = await execute_raw("DELETE FROM geo_regions", using="geo")
    _ = await execute_raw("DELETE FROM geo_buildings", using="geo")
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE generation = $1 AND osm_id >= 9200",
        [_GEN],
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE osm_type = 'gar'", using="geo"
    )
    _ = await execute_raw("DELETE FROM geo_address_enrich", using="geo")
    _ = await execute_raw(
        "DELETE FROM geo_enrich_queue WHERE kind IN "
        "('gar_unresolved', 'nspd_building_detail')",
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_source_cursors WHERE source = 'nspd'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_stats WHERE source = 'nspd'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_sources WHERE name = 'nspd'", using="geo"
    )


@pytest.fixture
async def _region() -> None:
    """Регион покрытия 0.02×0.04° — сетка 1×2 ячейки по ``nspd_cell_deg``."""
    now = datetime.now(UTC)
    _ = await GeoRegion.objects.create(
        instance=GeoRegion(
            name=_REGION,
            title="NSPD e2e",
            kind=GeoRegionKind.CUSTOM,
            bbox_south=55.745,
            bbox_west=37.59,
            bbox_north=55.765,
            bbox_east=37.63,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture
async def _seed_addresses() -> None:
    """Адрес внутри здания 77:01:0001001:1 — кандидат кадастровой привязки."""
    now = datetime.now(UTC)
    _ = await execute_raw(
        """
        INSERT INTO geo_addresses
            (osm_type, osm_id, display_name, city, street, housenumber,
             postcode, lat, lng, region, generation, source, gar_guid,
             canonical_name, cadastral_number, created_at)
        VALUES ('node', 9201, 'Тверская улица, 1', 'Москва',
                'Тверская улица', '1', '', 55.7600, 37.6120, $1, $2, 'osm',
                '', '', '', $3)
        """,
        [_REGION, _GEN, now],
        using="geo",
    )


@pytest.fixture
def settings() -> GeoSettings:
    return GeoSettings(
        nspd_base_url=_EMULATOR,
        nspd_cell_deg=0.02,
        nspd_tick_batch=1,
        nspd_rps=10.0,
        nspd_retry_pause_seconds=0.01,
        nspd_unresolved_defer_seconds=0.01,
    )


@pytest.fixture
def enrich_service(settings: GeoSettings) -> GeoEnrichService:
    return GeoEnrichService(settings)


@pytest.fixture
def service(
    settings: GeoSettings, enrich_service: GeoEnrichService
) -> NspdCrawlService:
    return NspdCrawlService(settings, enrich_service)


async def test_nspd_crawl_upserts_buildings_and_links_cadastral(
    service: NspdCrawlService, _region: None, _seed_addresses: None
) -> None:
    """Два тика покрывают сетку 1×2: здания в geo_buildings, адрес — кадастр."""
    result = await service.run_crawl()
    cell = result.regions[_REGION]
    assert cell["status"] == "running"
    assert cell["buildings"] == 1
    cursor = await GeoSourceCursor.by_source_region("nspd", _REGION)
    assert cursor is not None
    assert cursor.cursor == "1"
    assert cursor.status == GeoCursorStatus.RUNNING

    result = await service.run_crawl()
    cell = result.regions[_REGION]
    assert cell["status"] == "done"
    assert cell["buildings"] == 3
    assert cell["cadastral_links"] == 1
    cursor = await GeoSourceCursor.by_source_region("nspd", _REGION)
    assert cursor is not None
    assert cursor.status == GeoCursorStatus.DONE
    assert cursor.cursor == "2"

    building = await GeoBuilding.by_cadastral_number(
        cadastral_number="77:01:0001001:1"
    )
    assert building is not None
    assert building.region == _REGION
    assert abs(building.lat - 55.7600) < 0.001

    live = await execute_raw(
        "SELECT cadastral_number FROM geo_addresses WHERE osm_id = 9201",
        using="geo",
    )
    assert live[0]["cadastral_number"] == "77:01:0001001:1"
    enrich = await GeoAddressEnrich.by_object(osm_type="node", osm_id=9201)
    assert enrich is not None
    assert enrich.cadastral_number == "77:01:0001001:1"

    # Полный проход завершён: следующий тик начинает новый с нулевой ячейки.
    result = await service.run_crawl()
    assert result.regions[_REGION]["cells"] == 1


async def test_nspd_resolves_gar_unresolved_to_gen0_address(
    service: NspdCrawlService,
    enrich_service: GeoEnrichService,
    _region: None,
) -> None:
    """``gar_unresolved`` → search НСПД → gen-0 адрес source='gar' + enrich."""
    _ = await GeoEnrichItem.enqueue(
        kind="gar_unresolved",
        payload={
            "gar_objectid": "105",
            "gar_guid": "55555555-5555-5555-5555-555555555105",
            "canonical_name": "г. Москва, пл. Революции, д. 2",
            "street": "пл. Революции",
            "housenum": "2",
            "region": _REGION,
        },
    )
    drained = await enrich_service.drain()
    assert drained["done"] == 1

    rows = await execute_raw(
        "SELECT display_name, source, generation, lat, cadastral_number "
        "FROM geo_addresses WHERE osm_type = 'gar' AND osm_id = 105",
        using="geo",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "gar"
    assert row["generation"] == 0
    assert row["cadastral_number"] == "77:01:0001001:3"
    assert abs(float(str(row["lat"])) - 55.7570) < 0.001

    enrich = await GeoAddressEnrich.by_object(osm_type="gar", osm_id=105)
    assert enrich is not None
    assert enrich.gar_guid == "55555555-5555-5555-5555-555555555105"
    assert enrich.cadastral_number == "77:01:0001001:3"
    building = await GeoBuilding.by_cadastral_number(
        cadastral_number="77:01:0001001:3"
    )
    assert building is not None


async def test_nspd_unresolved_stays_parked_when_no_match(
    service: NspdCrawlService,
    enrich_service: GeoEnrichService,
    _region: None,
) -> None:
    """Промах резолва — defer: задача снова pending, payload не теряется."""
    _ = await GeoEnrichItem.enqueue(
        kind="gar_unresolved",
        payload={
            "gar_objectid": "777",
            "gar_guid": "77777777-7777-7777-7777-777777777777",
            "canonical_name": "г. Москва, ул. Несуществующая, д. 999",
            "street": "ул. Несуществующая",
            "housenum": "999",
            "region": _REGION,
        },
    )
    drained = await enrich_service.drain()
    assert drained["deferred"] == 1
    item = (
        await GeoEnrichItem.objects.filter(kind="gar_unresolved").first()
    )
    assert item is not None
    assert item.status == GeoEnrichStatus.PENDING


async def test_nspd_retry_recovers_from_flaky_500(settings: GeoSettings) -> None:
    """500 от API → backoff-retry клиента → следующий запрос успешен."""
    client = NspdClient(settings)
    async with get_httpx_client(timeout=10) as http:
        features = await client.search_buildings(
            http, query="flaky:77:01:0001001:3"
        )
    assert len(features) == 1
    options = features[0].properties["options"]
    assert isinstance(options, dict)
    assert options["cad_num"] == "77:01:0001001:3"


async def test_nspd_source_disabled_skips(
    service: NspdCrawlService, _region: None
) -> None:
    now = datetime.now(UTC)
    _ = await GeoSource.objects.create(
        instance=GeoSource(
            name="nspd",
            title="НСПД",
            kind=GeoSourceKind.REGISTRY,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
    )
    result = await service.run_crawl()
    assert result.skipped == "source_disabled"


async def test_nspd_referer_required() -> None:
    """Без Referer НСПД отвечает 403 — контрактная проверка эмулятора."""
    import httpx

    async with httpx.AsyncClient(base_url=_EMULATOR) as client:
        response = await client.get(
            "/api/geoportal/v2/search/geoportal",
            params={"query": "77:01:0001001:1"},
        )
    assert response.status_code == 403

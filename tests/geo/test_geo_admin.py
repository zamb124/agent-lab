"""Geo: правки админа — оверлеи, переживающие своп поколения.

``xdist_group("geo")``: модуль делит сид и поколение с test_geo_services.
Инвариант фазы: правка, записанная админом, применяется к живому
поколению мгновенно и перенакатывается импортёром на каждое следующее;
ручные адреса (generation=0) чистка импорта не трогает.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.api import GeoAddressUpdateRequest
from apps.geo.models.geo_address_override import GeoAddressOverride
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.geo_admin_service import GeoAdminService
from apps.geo.services.geo_coverage_service import GeoCoverageService
from apps.geo.services.osm_import_service import OsmImportService

_GEN = 990_000_001
_NEW_GEN = 990_000_002
_USER = "test-admin"

pytestmark = pytest.mark.xdist_group("geo")


@pytest.fixture(autouse=True)
def _test_generation(monkeypatch: pytest.MonkeyPatch):
    """Сервисы читают тестовое поколение, глобальная строка не трогается."""
    async def _gen(cls) -> int:  # noqa: ANN001 — сигнатуру диктует classmethod
        return _GEN

    monkeypatch.setattr(GeoImportState, "active_generation", classmethod(_gen))


@pytest.fixture(autouse=True)
async def _clean_overlays():
    """Оверлеи и manual-строки чисты на старте каждого теста."""
    for table in (
        "geo_address_overrides",
        "geo_address_enrich",
        "geo_suppressions",
        "geo_edge_overrides",
    ):
        _ = await execute_raw(f"DELETE FROM {table}", using="geo")
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE generation IN (0, $1)", [_NEW_GEN],
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE generation = $1 AND osm_id IN (9001, 9002)",
        [_GEN],
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_road_edges WHERE generation = $1", [_NEW_GEN],
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_road_edges WHERE generation = $1 AND osm_way_id = 777",
        [_GEN],
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_barriers WHERE generation = $1 AND osm_node_id = 555",
        [_GEN],
        using="geo",
    )


@pytest.fixture
async def admin() -> GeoAdminService:
    return GeoAdminService(GeoSettings())


@pytest.fixture
async def osm_addr():
    """Одна OSM-строка адреса в активном поколении."""
    _ = await execute_raw(
        """
        INSERT INTO geo_addresses (
            osm_type, osm_id, display_name, city, street, housenumber,
            postcode, lat, lng, region, generation, created_at
        ) VALUES ('node', 9001, 'Тверская улица, 1', 'Москва',
                  'Тверская улица', '1', '125009', 55.7501, 37.6173,
                  'moscow', $1, $2)
        ON CONFLICT (osm_type, osm_id, generation) DO NOTHING
        """,
        [_GEN, datetime.now(UTC)],
        using="geo",
    )
    return ("node", 9001)


async def test_manual_address_create_update_remove(admin: GeoAdminService) -> None:
    """Ручной адрес: gen0-строка с отрицательным osm_id правится и удаляется."""
    hit = await admin.create_address(
        display_name="Ручной адрес, 1",
        city="Москва",
        street="Тестовая",
        housenumber="1",
        postcode="",
        lat=55.75,
        lng=37.62,
        region="moscow",
        user_id=_USER,
    )
    assert hit.osm_type == "manual"
    assert hit.osm_id < 0

    updated = await admin.update_address(
        GeoAddressUpdateRequest(
            osm_type="manual", osm_id=hit.osm_id, housenumber="2"
        ),
        user_id=_USER,
    )
    assert updated.housenumber == "2"

    await admin.remove_address(
        osm_type="manual", osm_id=hit.osm_id, reason="тест", user_id=_USER
    )
    rows = await execute_raw(
        "SELECT count(*) AS c FROM geo_addresses WHERE osm_type = 'manual'",
        using="geo",
    )
    assert int(rows[0]["c"]) == 0


async def test_osm_update_writes_override_and_patches_live(
    admin: GeoAdminService, osm_addr
) -> None:
    """Правка OSM-строки: override с before-снапшотом + живой патч."""
    osm_type, osm_id = osm_addr
    updated = await admin.update_address(
        GeoAddressUpdateRequest(
            osm_type=osm_type,
            osm_id=osm_id,
            housenumber="1А",
            reason="уточнение",
        ),
        user_id=_USER,
    )
    assert updated.housenumber == "1А"

    override = await GeoAddressOverride.by_object(
        osm_type=osm_type, osm_id=osm_id
    )
    assert override is not None
    assert override.housenumber == "1А"
    assert override.before is not None
    assert override.before["housenumber"] == "1"
    assert override.updated_by == _USER


async def test_osm_remove_is_tombstone_and_revert_restores(
    admin: GeoAdminService, osm_addr
) -> None:
    """Тумбстоун скрывает адрес; откат восстанавливает его по before."""
    osm_type, osm_id = osm_addr
    await admin.remove_address(
        osm_type=osm_type, osm_id=osm_id, reason="ошибочный", user_id=_USER
    )
    rows = await execute_raw(
        "SELECT count(*) AS c FROM geo_addresses WHERE osm_id = $1",
        [osm_id],
        using="geo",
    )
    assert int(rows[0]["c"]) == 0

    restored = await admin.revert_override(osm_type=osm_type, osm_id=osm_id)
    assert restored is not None
    assert restored.housenumber == "1"
    assert await GeoAddressOverride.by_object(
        osm_type=osm_type, osm_id=osm_id
    ) is None


async def test_overrides_survive_generation_swap(
    admin: GeoAdminService, osm_addr
) -> None:
    """Ключевой инвариант: правка и тумбстоун переживают реимпорт поколения."""
    osm_type, osm_id = osm_addr
    await admin.update_address(
        GeoAddressUpdateRequest(
            osm_type=osm_type, osm_id=osm_id, housenumber="1Б"
        ),
        user_id=_USER,
    )
    osm_type2, osm_id2 = "node", 9002
    _ = await execute_raw(
        """
        INSERT INTO geo_addresses (
            osm_type, osm_id, display_name, city, street, housenumber,
            postcode, lat, lng, region, generation, created_at
        ) VALUES ($1, $2, 'Лишний адрес', 'Москва', 'Лишняя', '5',
                  '', 55.75, 37.62, 'moscow', $3, $4)
        ON CONFLICT (osm_type, osm_id, generation) DO NOTHING
        """,
        [osm_type2, osm_id2, _GEN, datetime.now(UTC)],
        using="geo",
    )
    await admin.remove_address(
        osm_type=osm_type2, osm_id=osm_id2, reason="лишний", user_id=_USER
    )

    # Реимпорт: те же OSM-объекты приходят в новом поколении исходными.
    _ = await execute_raw(
        """
        INSERT INTO geo_addresses (
            osm_type, osm_id, display_name, city, street, housenumber,
            postcode, lat, lng, region, generation, created_at
        ) VALUES
        ('node', 9001, 'Тверская улица, 1', 'Москва', 'Тверская улица', '1',
         '125009', 55.7501, 37.6173, 'moscow', $1, $2),
        ('node', 9002, 'Лишний адрес', 'Москва', 'Лишняя', '5',
         '', 55.75, 37.62, 'moscow', $1, $2)
        """,
        [_NEW_GEN, datetime.now(UTC)],
        using="geo",
    )
    importer = OsmImportService(GeoSettings(), GeoCoverageService(GeoSettings()))
    await importer._apply_overlays(_NEW_GEN)  # noqa: SLF001 — проверяем сам шаг

    rows = await execute_raw(
        "SELECT osm_id, housenumber FROM geo_addresses"
        " WHERE generation = $1 AND osm_id IN (9001, 9002) ORDER BY osm_id",
        [_NEW_GEN],
        using="geo",
    )
    assert len(rows) == 1
    assert int(rows[0]["osm_id"]) == 9001
    assert rows[0]["housenumber"] == "1Б"


async def test_enrich_applies_on_reimport_but_override_wins(
    admin: GeoAdminService, osm_addr
) -> None:
    """Приоритет: enrich-атрибуты источника → патч админа поверх."""
    from apps.geo.models.geo_address_enrich import GeoAddressEnrich

    osm_type, osm_id = osm_addr
    _ = await GeoAddressEnrich.upsert_by_object(
        GeoAddressEnrich(
            osm_type=osm_type,
            osm_id=osm_id,
            gar_guid="aaaa-bbbb",
            canonical_name="Москва, Тверская ул, 1",
            updated_at=datetime.now(UTC),
        )
    )
    _ = await execute_raw(
        """
        INSERT INTO geo_addresses (
            osm_type, osm_id, display_name, city, street, housenumber,
            postcode, lat, lng, region, generation, created_at
        ) VALUES ('node', 9001, 'Тверская улица, 1', 'Москва',
                  'Тверская улица', '1', '125009', 55.7501, 37.6173,
                  'moscow', $1, $2)
        """,
        [_NEW_GEN, datetime.now(UTC)],
        using="geo",
    )
    importer = OsmImportService(GeoSettings(), GeoCoverageService(GeoSettings()))
    await importer._apply_overlays(_NEW_GEN)  # noqa: SLF001

    rows = await execute_raw(
        "SELECT gar_guid, canonical_name, housenumber FROM geo_addresses"
        " WHERE generation = $1 AND osm_id = 9001",
        [_NEW_GEN],
        using="geo",
    )
    assert rows[0]["gar_guid"] == "aaaa-bbbb"
    assert rows[0]["canonical_name"] == "Москва, Тверская ул, 1"


async def test_edge_close_open_and_suppression(admin: GeoAdminService) -> None:
    """Закрытие way: costs -1 в живом поколении; снятие — только оверлей."""
    _ = await execute_raw(
        """
        INSERT INTO geo_road_edges (
            source, target, src_lat, src_lng, dst_lat, dst_lng, length_m,
            car_cost, car_reverse_cost, foot_cost, foot_reverse_cost,
            bike_cost, bike_reverse_cost, scooter_cost, scooter_reverse_cost,
            oneway, highway, name, osm_way_id, generation
        ) VALUES (1, 2, 55.75, 37.617, 55.75, 37.618, 100.0,
                  10, 10, 90, 90, 22, 22, 20, 20,
                  0, 'residential', 'тест', 777, $1)
        ON CONFLICT (generation, osm_way_id, source, target) DO NOTHING
        """,
        [_GEN],
        using="geo",
    )
    await admin.close_way(
        osm_way_id=777, modes=["car", "bike"], reason="ремонт", user_id=_USER
    )
    rows = await execute_raw(
        "SELECT car_cost, bike_cost, foot_cost FROM geo_road_edges"
        " WHERE osm_way_id = 777 AND generation = $1",
        [_GEN],
        using="geo",
    )
    assert int(rows[0]["car_cost"]) == -1
    assert int(rows[0]["bike_cost"]) == -1
    assert int(rows[0]["foot_cost"]) == 90

    await admin.open_way(osm_way_id=777)
    from apps.geo.models.geo_edge_override import GeoEdgeOverride

    assert await GeoEdgeOverride.by_way(osm_way_id=777) is None

    _ = await execute_raw(
        """
        INSERT INTO geo_barriers (
            osm_node_id, barrier, block_car, block_foot, block_bike,
            block_scooter, lat, lng, generation, created_at
        ) VALUES (555, 'bollard', true, false, false, false,
                  55.75, 37.62, $1, $2)
        ON CONFLICT (osm_node_id, generation) DO NOTHING
        """,
        [_GEN, datetime.now(UTC)],
        using="geo",
    )
    await admin.suppress_feature(
        entity="barrier", osm_id=555, reason="лишний", user_id=_USER
    )
    rows = await execute_raw(
        "SELECT count(*) AS c FROM geo_barriers"
        " WHERE osm_node_id = 555 AND generation = $1",
        [_GEN],
        using="geo",
    )
    assert int(rows[0]["c"]) == 0
    await admin.unsuppress_feature(entity="barrier", osm_id=555)

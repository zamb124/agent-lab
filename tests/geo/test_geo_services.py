"""Geo: адреса и маршруты на реальном PostGIS + pgRouting.

Весь модуль — ``xdist_group("geo")``: тесты делят сид одного поколения
и синглтон ``GeoImportState``, поэтому выполняются на одном воркере
последовательно. Сид — отдельное поколение ``_GEN``; активным его
делает monkeypatch ``active_generation`` в процессе теста, глобальная
строка импортёра живёт в собственных тестах.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_address import GeoAddress
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.geo_address_service import GeoAddressService
from apps.geo.services.geo_routing_service import GeoRoutingError, GeoRoutingService
from apps.geo.services.osm_import_service import OsmImportService

_GEN = 990_000_001
_FIXTURE = Path(__file__).parent / "fixtures" / "micro.osm"

pytestmark = pytest.mark.xdist_group("geo")

# Сетка 2x3: колонки ~62м, ряды ~111м на широте 55.75.
_NODES = {
    1: (55.75000, 37.61700),
    2: (55.75000, 37.61800),
    3: (55.75000, 37.61900),
    4: (55.75100, 37.61700),
    5: (55.75100, 37.61800),
    6: (55.75100, 37.61900),
    # motorway-сегмент в ~4.5км к северу — вне snap_max_distance_m=3000 пешего графа
    7: (55.79000, 37.61700),
    8: (55.79000, 37.61900),
}

# (src, dst, car_f, car_r, foot_f, foot_r, bike_f, bike_r, scoot_f, scoot_r, highway, oneway)
_EDGES = [
    (1, 2, 10, 10, 90, 90, 22, 22, 20, 20, "residential", 0),
    (2, 3, 10, -1, 90, 90, 22, -1, 20, -1, "residential", 1),   # oneway car/bike/scooter
    (1, 4, 10, 10, 90, 90, 22, 22, 20, 20, "residential", 0),
    (4, 5, 10, 10, 90, 90, 22, 22, 20, 20, "residential", 0),
    (4, 5, -1, -1, 60, 60, 45, 45, 40, 40, "footway", 0),        # параллельно residential
    (2, 5, 10, 10, 90, 90, 22, 22, 20, 20, "residential", 0),
    (5, 6, 10, 10, 90, 90, 22, 22, 20, 20, "residential", 0),
    (6, 3, 10, 10, 90, 90, 22, 22, 20, 20, "residential", 0),
    (7, 8, 12, 12, -1, -1, -1, -1, -1, -1, "motorway", 0),       # только car
]

_ADDRESSES = [
    ("node", 1001, "Тверская улица, 1", "Москва", "Тверская улица", "1", "125009", 55.75010, 37.61730),
    ("node", 1002, "Тверская улица, 3", "Москва", "Тверская улица", "3", "", 55.75030, 37.61780),
    ("node", 1003, "Никольская улица, 10", "Москва", "Никольская улица", "10", "", 55.75060, 37.61840),
    ("node", 1004, "Арбат, 5", "Москва", "Арбат", "5", "", 55.74900, 37.59200),
    # ровно на нижней кромке зоны: ST_Covers считает границу внутри
    ("node", 1005, "Тверская улица, 7", "Москва", "Тверская улица", "7", "", 55.75000, 37.61750),
]

_ZONE = json.dumps(
    {
        "type": "Polygon",
        "coordinates": [
            [
                [37.61700, 55.75000],
                [37.61850, 55.75000],
                [37.61850, 55.75100],
                [37.61700, 55.75100],
                [37.61700, 55.75000],
            ]
        ],
    }
)


@pytest.fixture(autouse=True)
def _test_generation(monkeypatch: pytest.MonkeyPatch):
    """Сервисы читают тестовое поколение, глобальная строка не трогается."""
    async def _gen(cls) -> int:  # noqa: ANN001 — сигнатуру диктует classmethod
        return _GEN

    monkeypatch.setattr(GeoImportState, "active_generation", classmethod(_gen))


@pytest.fixture(scope="module")
async def geo_seed():
    """Поколение _GEN: детерминированный граф и справочник адресов."""
    for table in ("geo_road_edges", "geo_road_vertices", "geo_addresses"):
        _ = await execute_raw(
            f"DELETE FROM {table} WHERE generation = $1", [_GEN], using="geo"
        )
    _ = await execute_raw(
        """
        INSERT INTO geo_road_vertices (node_id, lat, lng, generation)
        SELECT node_id, lat, lng, $1
        FROM (VALUES (1,55.75000,37.61700),(2,55.75000,37.61800),(3,55.75000,37.61900),
                    (4,55.75100,37.61700),(5,55.75100,37.61800),(6,55.75100,37.61900),
                    (7,55.79000,37.61700),(8,55.79000,37.61900)
             ) AS v(node_id, lat, lng)
        """,
        [_GEN],
        using="geo",
    )
    for way_id, (src, dst, cf, cr, ff, fr, bf, br, sf, sr, highway, oneway) in enumerate(
        _EDGES, start=1
    ):
        a, b = _NODES[src], _NODES[dst]
        _ = await execute_raw(
            """
            INSERT INTO geo_road_edges (
                source, target, src_lat, src_lng, dst_lat, dst_lng, length_m,
                car_cost, car_reverse_cost, foot_cost, foot_reverse_cost,
                bike_cost, bike_reverse_cost, scooter_cost, scooter_reverse_cost,
                oneway, highway, name, osm_way_id, generation
            ) VALUES (
                $1,$2,$3,$4,$5,$6,100.0,
                $7,$8,$9,$10,$11,$12,$13,$14,
                $15,$16,'тест',$17,$18
            )
            """,
            [src, dst, a[0], a[1], b[0], b[1], cf, cr, ff, fr, bf, br, sf, sr,
             oneway, highway, way_id, _GEN],
            using="geo",
        )
    for (osm_type, osm_id, name, city, street, house, postcode, lat, lng) in _ADDRESSES:
        _ = await execute_raw(
            """
            INSERT INTO geo_addresses (
                osm_type, osm_id, display_name, city, street, housenumber,
                postcode, lat, lng, generation, created_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            [osm_type, osm_id, name, city, street, house, postcode, lat, lng,
             _GEN, datetime.now(UTC)],
            using="geo",
        )
    return _GEN


@pytest.fixture
def addresses() -> GeoAddressService:
    return GeoAddressService(GeoSettings())


@pytest.fixture
def routing() -> GeoRoutingService:
    return GeoRoutingService(GeoSettings())


async def test_addresses_in_zone_exact_list(
    geo_seed, addresses: GeoAddressService
) -> None:
    """ST_Covers: 3 внутри + 1 на границе; Арбат снаружи не попадает."""
    result = await addresses.addresses_in_zone_by_name_asc(
        zone_geojson=_ZONE, query=None, limit=50, offset=0
    )
    names = {a.display_name for a in result.items}
    assert result.total == 4
    assert names == {
        "Тверская улица, 1",
        "Тверская улица, 3",
        "Никольская улица, 10",
        "Тверская улица, 7",
    }


async def test_addresses_in_zone_query_and_page(
    geo_seed, addresses: GeoAddressService
) -> None:
    """Фильтр q и пагинация: total — полный счёт, items — страница."""
    page = await addresses.addresses_in_zone_by_name_asc(
        zone_geojson=_ZONE, query="Тверская", limit=2, offset=1
    )
    assert page.total == 3
    assert len(page.items) == 2
    assert all("Тверская" in a.display_name for a in page.items)


async def test_suggest(geo_seed, addresses: GeoAddressService) -> None:
    hits = await addresses.suggest_by_score_desc(
        query="Тверская", zone_geojson=None, lat=None, lng=None, limit=5
    )
    assert [h.display_name for h in hits] == [
        "Тверская улица, 1",
        "Тверская улица, 3",
        "Тверская улица, 7",
    ]


async def test_nearest(geo_seed, addresses: GeoAddressService) -> None:
    hits = await addresses.nearest_by_distance(lat=55.75010, lng=37.61732, limit=1)
    assert len(hits) == 1
    assert hits[0].display_name == "Тверская улица, 1"


async def test_route_modes_differ(geo_seed, routing: GeoRoutingService) -> None:
    """Один маршрут A→C: car быстрее bike, scooter едет по гибридному графу."""
    car = await routing.calculate(
        from_lat=55.75000, from_lng=37.61700, to_lat=55.75000, to_lng=37.61900, mode="car"
    )
    foot = await routing.calculate(
        from_lat=55.75000, from_lng=37.61700, to_lat=55.75000, to_lng=37.61900, mode="foot"
    )
    bike = await routing.calculate(
        from_lat=55.75000, from_lng=37.61700, to_lat=55.75000, to_lng=37.61900, mode="bike"
    )
    scooter = await routing.calculate(
        from_lat=55.75000, from_lng=37.61700, to_lat=55.75000, to_lng=37.61900, mode="scooter"
    )
    assert car.duration_s == pytest.approx(20.0)
    assert foot.duration_s == pytest.approx(180.0)
    assert bike.duration_s == pytest.approx(44.0)
    assert scooter.duration_s == pytest.approx(40.0)
    assert car.geometry is not None and car.geometry["type"] == "LineString"


async def test_oneway_reverse_goes_around(geo_seed, routing: GeoRoutingService) -> None:
    """C→B против oneway: объезд C-F-E-B (30s), не реверс запрещённого ребра."""
    route = await routing.calculate(
        from_lat=55.75000, from_lng=37.61900, to_lat=55.75000, to_lng=37.61800, mode="car"
    )
    assert route.duration_s == pytest.approx(30.0)


async def test_foot_uses_footway_shortcut(geo_seed, routing: GeoRoutingService) -> None:
    """footway-параллель residential: foot режим выбирает короткий тротуар."""
    route = await routing.calculate(
        from_lat=55.75100, from_lng=37.61700, to_lat=55.75100, to_lng=37.61800, mode="foot"
    )
    assert route.duration_s == pytest.approx(60.0)


async def test_mode_aware_snap(geo_seed, routing: GeoRoutingService) -> None:
    """Car снапится к motorway; foot игнорирует его, а до пешего графа >3км → too far."""
    car = await routing.calculate(
        from_lat=55.79000, from_lng=37.61700, to_lat=55.79000, to_lng=37.61900, mode="car"
    )
    assert car.duration_s == pytest.approx(12.0)
    with pytest.raises(GeoRoutingError) as exc:
        await routing.calculate(
            from_lat=55.79000, from_lng=37.61700, to_lat=55.79000, to_lng=37.61900, mode="foot"
        )
    assert exc.value.code == "point_too_far_from_road"


async def test_route_not_found_is_domain_error(
    geo_seed, routing: GeoRoutingService
) -> None:
    """Точка вне графа (>snap_max от любого ребра) — point_too_far, не молчание."""
    with pytest.raises(GeoRoutingError) as exc:
        await routing.calculate(
            from_lat=55.90000, from_lng=37.00000, to_lat=55.90010, to_lng=37.00010, mode="car"
        )
    assert exc.value.code == "point_too_far_from_road"


async def test_matrix(geo_seed, routing: GeoRoutingService) -> None:
    matrix = await routing.matrix(
        sources=[(55.75000, 37.61700), (55.75000, 37.61800)],
        targets=[(55.75000, 37.61700), (55.75000, 37.61900)],
        mode="car",
    )
    assert matrix.durations_s == [[0.0, 20.0], [10.0, 10.0]]
    assert matrix.distances_m[0][0] == 0.0


async def test_optimal_order(geo_seed, routing: GeoRoutingService) -> None:
    order = await routing.optimal_order(
        start=(55.75000, 37.61700),
        points=[(55.75100, 37.61700), (55.75000, 37.61900), (55.75100, 37.61800)],
        mode="car",
        with_legs=True,
    )
    assert sorted(order.order) == [0, 1, 2]
    assert len(order.legs) == 4  # старт -> 3 точки -> возврат к старту
    assert order.total_duration_s > 0


async def test_isochrone(geo_seed, routing: GeoRoutingService) -> None:
    iso = await routing.isochrone(lat=55.75000, lng=37.61700, minutes=3, mode="car")
    assert iso.reachable_vertices >= 4
    assert iso.polygon is not None


async def test_import_osm_fixture_and_generation_swap() -> None:
    """Полный цикл: file:// экстракт → pyosmium → bulk → атомарный своп поколения."""
    state = await GeoImportState.get_state()
    if state is not None:
        state.source_modified_at = None
        state.current_generation = 0
        _ = await state.save()
    settings = GeoSettings(
        osm_extract_urls=[f"file://{_FIXTURE}"],
    )
    result = await OsmImportService(settings).run_sync()
    assert result["imported"] is True
    assert result["rows_addresses"] == 4
    assert result["rows_vertices"] == 8
    assert result["rows_edges"] == 9
    assert _FIXTURE.is_file()  # file://-источник не удаляется

    state = await GeoImportState.get_state()
    assert state is not None and state.current_generation > 0
    gen = state.current_generation

    addr = await GeoAddress.objects.filter(generation=gen).all()
    assert {a.display_name for a in addr} == {
        "Москва, Тверская улица, 1",
        "Москва, Тверская улица, 3",
        "Москва, Никольская улица, 10",
        "Москва, Арбат, 5",
    }
    # mode-стоимости импортёра на реальных тегах
    edges = await execute_raw(
        "SELECT highway, oneway, car_cost, car_reverse_cost, foot_cost,"
        " foot_reverse_cost, bike_cost, bike_reverse_cost, scooter_cost"
        " FROM geo_road_edges WHERE generation = $1 AND osm_way_id = $2",
        [gen, 11],  # oneway residential
        using="geo",
    )
    assert edges and edges[0]["car_reverse_cost"] == -1
    assert edges[0]["bike_reverse_cost"] == -1
    assert edges[0]["foot_reverse_cost"] > 0  # пешеходу oneway не закон
    motor = await execute_raw(
        "SELECT car_cost, foot_cost, bike_cost, scooter_cost FROM geo_road_edges"
        " WHERE generation = $1 AND highway = 'motorway'",
        [gen],
        using="geo",
    )
    assert motor and motor[0]["car_cost"] > 0
    assert motor[0]["foot_cost"] == -1
    assert motor[0]["bike_cost"] == -1
    assert motor[0]["scooter_cost"] == -1
    footway = await execute_raw(
        "SELECT car_cost, foot_cost FROM geo_road_edges"
        " WHERE generation = $1 AND highway = 'footway'",
        [gen],
        using="geo",
    )
    assert footway and footway[0]["car_cost"] == -1
    assert footway[0]["foot_cost"] > 0


async def test_import_rerun_is_idempotent() -> None:
    """Повторный run_sync без смены mtime → not_modified, второго поколения нет."""
    before = await GeoImportState.get_state()
    assert before is not None and before.current_generation > 0
    result = await OsmImportService(
        GeoSettings(osm_extract_urls=[f"file://{_FIXTURE}"])
    ).run_sync()
    assert result == {"skipped": True, "reason": "not_modified"}

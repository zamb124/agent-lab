"""Строгий e2e in-memory роутинг-движка поверх реальной БД.

Покрытие слепых зон, которые поведенческие тесты сервиса не трогают:

- кэш графа по (mode, generation) и ``invalidate()``;
- инвалидация из админ-правок end-to-end (close_way → маршрут меняется
  без ре-импорта, на том же engine-инстансе, что у роутинг-сервиса);
- паритет ``only_*`` рестрикций: запрет применяется только к въездам
  с ``from_way``, остальные въезды свободны;
- u-turn на гаджет-вершине не запрещён (TRSP ``t.id <> f.id``);
- gadget-переходы не попадают в плечи пути (только реальные рёбра);
- недостижимые ячейки матрицы — None, а не мусор;
- изохрона: достижимость ограничена cutoff'ом.

``xdist_group("geo")`` — сид и поколение общие с остальными geo-модулями.
"""

from __future__ import annotations

import asyncio

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.geo_admin_service import GeoAdminService
from apps.geo.services.geo_routing_service import GeoRoutingService
from apps.geo.services.routing.engine import GeoRoutingEngine
from core.errors.boundary import PlatformUnavailableError

pytestmark = pytest.mark.xdist_group("geo")

_GEN = 990_000_001
_USER = "test-admin"

# Сетка 2x3 + изолированная пара (9,10) в радиусе snap, но не связанная с
# графом — носитель недостижимых ячеек матрицы.
_NODES = {
    1: (55.75000, 37.61700),
    2: (55.75000, 37.61800),
    3: (55.75000, 37.61900),
    4: (55.75100, 37.61700),
    5: (55.75100, 37.61800),
    6: (55.75100, 37.61900),
    9: (55.75000, 37.62100),
    10: (55.75050, 37.62150),
}

# (src, dst, car_f, car_r, osm_way_id)
# way 3 (1→4) дешевле (5s) — прямой маршрут идёт через него, иначе 30-40s.
_EDGES = [
    (1, 2, 10, 10, 1),
    (2, 3, 10, -1, 2),   # oneway car
    (1, 4, 5, 5, 3),
    (4, 5, 10, 10, 4),
    (2, 5, 10, 10, 5),
    (5, 6, 10, 10, 6),
    (6, 3, 10, 10, 7),
    (9, 10, 10, 10, 9),
]


@pytest.fixture(autouse=True)
def _test_generation(monkeypatch: pytest.MonkeyPatch):
    """Сервисы читают тестовое поколение, глобальная строка не трогается."""

    async def _gen(_cls: type[GeoImportState]) -> int:
        return _GEN

    monkeypatch.setattr(GeoImportState, "active_generation", classmethod(_gen))


@pytest.fixture(scope="module", autouse=True)
async def _engine_seed():
    """Поколение _GEN: асимметричный car-граф + изолированная компонента."""
    for table in (
        "geo_road_edges",
        "geo_road_vertices",
        "geo_turn_restrictions",
        "geo_barriers",
        "geo_traffic_signals",
    ):
        _ = await execute_raw(
            f"DELETE FROM {table} WHERE generation = $1", [_GEN], using="geo"
        )
    for table in ("geo_edge_overrides", "geo_suppressions"):
        _ = await execute_raw(f"DELETE FROM {table}", using="geo")
    _ = await execute_raw(
        """
        INSERT INTO geo_road_vertices (node_id, lat, lng, generation)
        SELECT node_id, lat, lng, $1
        FROM (VALUES (1,55.75000,37.61700),(2,55.75000,37.61800),(3,55.75000,37.61900),
                    (4,55.75100,37.61700),(5,55.75100,37.61800),(6,55.75100,37.61900),
                    (9,55.75000,37.62100),(10,55.75050,37.62150)
             ) AS v(node_id, lat, lng)
        """,
        [_GEN],
        using="geo",
    )
    for src, dst, cf, cr, way_id in _EDGES:
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
                $7,$8,90,90,22,22,20,20,
                0,'residential','тест',$9,$10
            )
            """,
            [src, dst, a[0], a[1], b[0], b[1], cf, cr, way_id, _GEN],
            using="geo",
        )


@pytest.fixture
def engine() -> GeoRoutingEngine:
    return GeoRoutingEngine(GeoSettings())


@pytest.fixture
def routing(engine: GeoRoutingEngine) -> GeoRoutingService:
    return GeoRoutingService(GeoSettings(), engine)


@pytest.fixture
def admin(engine: GeoRoutingEngine) -> GeoAdminService:
    return GeoAdminService(GeoSettings(), engine)


async def test_graph_cached_then_invalidate_rebuilds(
    engine: GeoRoutingEngine,
) -> None:
    """Один ключ (mode, generation) — один объект; invalidate → пересборка."""
    first = await engine.graph("car", _GEN)
    second = await engine.graph("car", _GEN)
    assert first is second
    foot = await engine.graph("foot", _GEN)
    assert foot is not first

    engine.invalidate()
    rebuilt = await engine.graph("car", _GEN)
    assert rebuilt is not first

    with pytest.raises(PlatformUnavailableError):
        _ = await engine.graph("car", _GEN + 900)


async def test_close_way_reroutes_without_reimport(
    routing: GeoRoutingService, admin: GeoAdminService
) -> None:
    """Shared-engine e2e: close_way инвалидирует граф — маршрут объезжает.

    Базово 1→6 через дешёвый way 3 (1→4): 5+10+10 = 25s.
    Закрытие way 3 → дешёвого выезда из 1 нет: 1→2→…→6 = 30s.
    """
    direct = await routing.calculate(
        from_lat=55.75000, from_lng=37.61700,
        to_lat=55.75100, to_lng=37.61900, mode="car",
    )
    assert direct.duration_s == pytest.approx(25.0)

    await admin.close_way(
        osm_way_id=3, modes=["car"], reason="ремонт", user_id=_USER
    )
    try:
        detour = await routing.calculate(
            from_lat=55.75000, from_lng=37.61700,
            to_lat=55.75100, to_lng=37.61900, mode="car",
        )
        assert detour.duration_s == pytest.approx(30.0)
    finally:
        await admin.open_way(osm_way_id=3)
        # open_way снимает оверлей; живые costs лечит следующее поколение —
        # тест сам возвращает их, чтобы не портить граф соседним тестам.
        _ = await execute_raw(
            "UPDATE geo_road_edges SET car_cost = 5, car_reverse_cost = 5"
            + " WHERE generation = $1 AND osm_way_id = 3",
            [_GEN],
            using="geo",
        )
        routing._engine.invalidate()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


async def test_only_turn_scoped_to_from_way(
    routing: GeoRoutingService,
) -> None:
    """``only_*`` вяжет (from_way → to_way): въезды с других way свободны.

    only_right_turn(from=way4, to=way5, via=5): приезд в 5 по way4 обязан
    выехать way5. Маршрут 2→6 (въезд по way5) рестрикции не подчиняется —
    прямые 20s; маршрут 4→6 (въезд по way4) объезжает.
    """
    _ = await execute_raw(
        """
        INSERT INTO geo_turn_restrictions
            (osm_relation_id, from_way, to_way, via_node, restriction,
             region, generation, created_at)
        VALUES (9901, 4, 5, 5, 'only_right_turn', 'test', $1, now())
        """,
        [_GEN],
        using="geo",
    )
    try:
        free = await routing.calculate(
            from_lat=55.75000, from_lng=37.61800,
            to_lat=55.75100, to_lng=37.61900, mode="car",
        )
        assert free.duration_s == pytest.approx(20.0)

        forced = await routing.calculate(
            from_lat=55.75100, from_lng=37.61700,
            to_lat=55.75100, to_lng=37.61900, mode="car",
        )
        assert 20.0 < forced.duration_s < 1e9
    finally:
        _ = await execute_raw(
            "DELETE FROM geo_turn_restrictions WHERE generation = $1",
            [_GEN],
            using="geo",
        )


async def test_u_turn_at_signal_vertex_not_forbidden(
    routing: GeoRoutingService,
) -> None:
    """Разворот по тому же ребру на special-вершине — без FORBIDDEN-штрафа.

    Светофор на узле 6 делает его гаджет-вершиной. Точка на ребре 5→6 у
    самой вершины 6: путь к 5 идёт разворотом по тому же ребру — если
    u-turn штрафовался FORBIDDEN, длительность улетит за 1e12.
    """
    _ = await execute_raw(
        """
        INSERT INTO geo_traffic_signals
            (osm_node_id, lat, lng, generation, created_at)
        VALUES (6, 55.75100, 37.61900, $1, now())
        """,
        [_GEN],
        using="geo",
    )
    try:
        route = await routing.calculate(
            from_lat=55.75099, from_lng=37.61890,
            to_lat=55.75100, to_lng=37.61800, mode="car",
        )
        assert route.duration_s < 60.0
    finally:
        _ = await execute_raw(
            "DELETE FROM geo_traffic_signals WHERE generation = $1",
            [_GEN],
            using="geo",
        )


async def test_path_legs_are_real_edges_only(
    routing: GeoRoutingService, engine: GeoRoutingEngine
) -> None:
    """Плечи пути — только настоящие рёбра: gadget-переходы отфильтрованы."""
    _ = await execute_raw(
        """
        INSERT INTO geo_barriers
            (osm_node_id, barrier, block_car, block_foot, block_bike,
             block_scooter, lat, lng, region, generation, created_at)
        VALUES (5, 'bollard', false, false, false, false,
                55.75100, 37.61800, 'test', $1, now())
        """,
        [_GEN],
        using="geo",
    )
    try:
        engine.invalidate()
        graph = await engine.graph("car", _GEN)
        # Маршрут пересекает узел 5 (барьер без блокировок — гаджет есть,
        # переходы нулевые): половина way3 + way4 + половина way6.
        start_snap = await routing._snap_edge(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            55.75050, 37.61700, mode="car", generation=_GEN
        )
        end_snap = await routing._snap_edge(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            55.75100, 37.61850, mode="car", generation=_GEN
        )
        path = await asyncio.to_thread(
            engine.path,
            graph,
            GeoRoutingService._edge_point(start_snap),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            GeoRoutingService._edge_point(end_snap),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        )
        assert path is not None
        assert path.total_cost == pytest.approx(17.5)  # .5*5 + 10 + .5*10
        assert len(path.legs) == 3  # полу-плечи + полное ребро через гаджет
        for leg in path.legs:
            assert leg.edge_id > 0
            assert 0.0 <= leg.frac_from < leg.frac_to <= 1.0
        assert path.legs[0].frac_from == pytest.approx(0.5)
        assert path.legs[0].frac_to == 1.0
        assert path.legs[-1].frac_from == 0.0
        assert path.legs[-1].frac_to == pytest.approx(0.5)
        mid = path.legs[1]
        assert mid.frac_from == 0.0 and mid.frac_to == 1.0
    finally:
        _ = await execute_raw(
            "DELETE FROM geo_barriers WHERE generation = $1 AND osm_node_id = 5",
            [_GEN],
            using="geo",
        )
        engine.invalidate()


async def test_matrix_unreachable_cells_are_none(
    routing: GeoRoutingService,
) -> None:
    """Связанный snap, но несвязанные компоненты → None-ячейка, не мусор."""
    matrix = await routing.matrix(
        sources=[(55.75000, 37.61700), (55.75000, 37.62100)],
        targets=[(55.75000, 37.61700)],
        mode="car",
    )
    assert matrix.durations_s[0][0] == pytest.approx(0.0)
    assert matrix.durations_s[1][0] is None
    assert matrix.distances_m[1][0] is None


async def test_isochrone_excludes_disconnected_component(
    routing: GeoRoutingService,
) -> None:
    """Изохрона: только достижимые вершины cutoff'а; 9/10 не входят."""
    iso = await routing.isochrone(
        lat=55.75000, lng=37.61700, minutes=5, mode="car"
    )
    assert iso.reachable_vertices == 6  # узлы 1-6; изолированные 9,10 — нет
    assert iso.polygon is not None
    assert iso.polygon["type"] in ("Polygon", "MultiPolygon")

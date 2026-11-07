"""Импорт OSM-экстрактов в справочник адресов и дорожный граф.

Конвейер ``run_sync``: If-Modified-Since → stream-download → pyosmium
(три прохода: нужные ноды → локации → строки) → batch INSERT в
``generation=N+1`` → атомарный своп ``current_generation`` → чистка старых
поколений. Падение на любом шаге оставляет прошлое поколение живым —
запросы продолжают обслуживаться.

Читаются и ``.osm.pbf``, и ``.osm`` (XML) — тесты ходят по XML-фикстуре
без бинарного PBF.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import osmium
from osmium.osm import Node, Relation, Way, osm_entity_bits
from oxyde import execute_raw
from pydantic import BaseModel

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.models.geo_region import GeoRegion
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services.geo_coverage_service import GeoCoverageService
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.http import get_httpx_client
from core.logging import get_logger
from core.tasks import enqueue
from core.types import SqlParameterValue

if TYPE_CHECKING:
    from osmium.osm import NodeRef, TagList

logger = get_logger(__name__)

# highway-классы, исключаемые из графа вообще
_HIGHWAY_SKIP = frozenset(
    {"proposed", "construction", "raceway", "corridor", "elevator", "escape", "bus_guideway"}
)
# Классы только для мототранспорта: foot/bike/scooter проходят лишь по
# явному разрешению (foot=yes / bicycle=yes).
_MOTOR_ONLY = frozenset({"motorway", "motorway_link", "trunk", "trunk_link"})
# Пешие/лёгкие классы: на них oneway распространяется и на пешехода.
_PATH_CLASSES = frozenset(
    {"path", "track", "footway", "pedestrian", "steps", "cycleway", "bridleway"}
)
_ACCESS_DENY = frozenset({"no", "private"})
_ACCESS_ALLOW = frozenset(
    {"yes", "true", "1", "designated", "official", "permissive", "destination", "customers", "public"}
)
_ONEWAY_YES = frozenset({"yes", "true", "1"})
_ONEWAY_NO = frozenset({"no", "false", "0"})
_EARTH_R = 6_371_000.0
_ENTITY_BITS = (
    osm_entity_bits.NODE | osm_entity_bits.WAY | osm_entity_bits.RELATION
)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * _EARTH_R * asin(sqrt(a))


def _display_name(tags: TagList) -> str | None:
    housenumber = tags.get("addr:housenumber")
    street = tags.get("addr:street")
    if not housenumber or not street:
        return None
    city = tags.get("addr:city") or tags.get("addr:place") or tags.get("addr:suburb") or ""
    return ", ".join(part for part in (city, street, housenumber) if part)


def _access_allowed(tags: TagList, key: str, default: bool) -> bool:
    """Доступность режима по тегам: явный deny/allow важнее общего ``access``."""
    explicit = tags.get(key)
    if explicit in _ACCESS_DENY:
        return False
    if explicit in _ACCESS_ALLOW:
        return True
    return default and tags.get("access") not in _ACCESS_DENY


def _dir_override(tag_val: str | None, default: int) -> int:
    """Направление из ``oneway*``-тега: 1 прямое, -1 обратное, 0 обе."""
    if tag_val in _ONEWAY_YES:
        return 1
    if tag_val == "-1":
        return -1
    if tag_val in _ONEWAY_NO:
        return 0
    return default


def _has_opposite_cycleway(tags: TagList) -> bool:
    """Встречная велополоса на односторонней дороге → bike/scooter двунаправлены."""
    for key in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both"):
        if "opposite" in (tags.get(key) or ""):
            return True
    return False


# Проходимость барьера по режимам (car, foot, bike, scooter): True — режим
# заблокирован. Открытые типы («проход есть») и контрольные без запрета —
# не блокируют никого; неизвестные типы — консервативно всем запрет.
_BARRIER_OPEN = frozenset(
    {"yes", "entrance", "opening", "toll_booth", "cattle_grid", "bump_gate", "no"}
)
_BARRIER_BLOCKS: dict[str, tuple[bool, bool, bool, bool]] = {
    "gate": (True, True, True, True),
    "lift_gate": (True, True, True, True),
    "swing_gate": (True, True, True, True),
    "sliding_gate": (True, True, True, True),
    "folding_gate": (True, True, True, True),
    "hampshire_gate": (True, True, True, True),
    "door": (True, True, True, True),
    "turnstile": (True, False, True, True),
    "full_turnstile": (True, False, True, True),
    "stile": (True, False, True, True),
    "kissing_gate": (True, False, True, True),
    "squeezer": (True, False, True, True),
    "wicket_gate": (True, False, True, True),
    "motorcycle_barrier": (True, False, True, True),
    "cycle_barrier": (True, False, True, True),
    "bollard": (True, False, False, False),
    "block": (True, False, True, True),
    "jersey_barrier": (True, False, True, True),
    "boulder": (True, False, True, True),
    "debris": (True, False, True, True),
    "log": (True, False, True, True),
    "chain": (True, False, False, False),
    "rope": (True, False, False, False),
    "kerb": (True, False, False, True),
    "fence": (True, True, True, True),
    "wall": (True, True, True, True),
    "hedge": (True, True, True, True),
    "ditch": (True, True, True, True),
    "guard_rail": (True, True, True, True),
    "retaining_wall": (True, True, True, True),
    "city_wall": (True, True, True, True),
    "embankment": (True, True, True, True),
}
_BARRIER_BLOCK_ALL = (True, True, True, True)


def _barrier_blocks(tags: TagList, barrier: str) -> tuple[bool, bool, bool, bool]:
    """Флаги блокировки режимов барьером: тип + access-override'ы.

    Открытые типы не блокируют никого; неизвестные — консервативно всем.
    ``access``/``locked`` и ключи режимов переопределяют дефолт типа;
    scooter следует за bicycle (OSM-тега scooter почти нет).
    """
    if barrier in _BARRIER_OPEN:
        car, foot, bike, scooter = False, False, False, False
    else:
        car, foot, bike, scooter = _BARRIER_BLOCKS.get(barrier, _BARRIER_BLOCK_ALL)
    access = tags.get("access")
    if access in _ACCESS_ALLOW:
        car = foot = bike = scooter = False
    elif access in _ACCESS_DENY or tags.get("locked") in _ONEWAY_YES:
        car = foot = bike = scooter = True
    for key in ("motor_vehicle", "motorcar", "vehicle"):
        val = tags.get(key)
        if val in _ACCESS_ALLOW:
            car = False
        elif val in _ACCESS_DENY:
            car = True
    foot_tag = tags.get("foot")
    if foot_tag in _ACCESS_ALLOW:
        foot = False
    elif foot_tag in _ACCESS_DENY:
        foot = True
    bicycle_tag = tags.get("bicycle")
    if bicycle_tag in _ACCESS_ALLOW:
        bike = scooter = False
    elif bicycle_tag in _ACCESS_DENY:
        bike = scooter = True
    return car, foot, bike, scooter


class _ModeCosts:
    """Пары (cost, reverse_cost) секунд для каждого режима одного ребра."""

    __slots__: tuple[str, str, str, str] = ("car", "foot", "bike", "scooter")

    def __init__(self) -> None:
        self.car: tuple[float, float] = (-1.0, -1.0)
        self.foot: tuple[float, float] = (-1.0, -1.0)
        self.bike: tuple[float, float] = (-1.0, -1.0)
        self.scooter: tuple[float, float] = (-1.0, -1.0)

    def any_passable(self) -> bool:
        return any(
            c > 0 or r > 0
            for c, r in (self.car, self.foot, self.bike, self.scooter)
        )


def _sec(length_m: float, kmh: float) -> float:
    return length_m / (kmh / 3.6)


def _maxspeed_kmh(raw: str | None) -> float | None:
    """Численный лимит ``maxspeed`` в км/ч: '50', '50 mph', '30 km/h'.

    Зональные значения ('RU:urban', 'none', 'walk') числом не являются —
    возвращаем ``None`` и остаётся скорость класса highway. Лимиты вне
    1–200 км/ч считаем мусором OSM.
    """
    if raw is None:
        return None
    v = raw.strip().lower()
    mult = 1.0
    for suffix, m in (("mph", 1.60934), ("km/h", 1.0), ("kmh", 1.0), ("kph", 1.0)):
        if v.endswith(suffix):
            mult, v = m, v[: -len(suffix)]
            break
    try:
        kmh = float(v.strip()) * mult
    except ValueError:
        return None
    return kmh if 1.0 <= kmh <= 200.0 else None


def _pair(length_m: float, kmh: float | None, direction: int) -> tuple[float, float]:
    """(cost, reverse_cost): direction 0 — обе, 1 — прямое, -1 — обратное."""
    if not kmh:
        return -1.0, -1.0
    sec = _sec(length_m, kmh)
    if direction == 1:
        return sec, -1.0
    if direction == -1:
        return -1.0, sec
    return sec, sec


def _pair_dirs(
    length_m: float, kmh_f: float | None, kmh_r: float | None, direction: int
) -> tuple[float, float]:
    """``_pair`` с разными скоростями направлений (``maxspeed:forward/backward``)."""
    sec_f = _sec(length_m, kmh_f) if kmh_f else -1.0
    sec_r = _sec(length_m, kmh_r) if kmh_r else -1.0
    if direction == 1:
        return sec_f, -1.0
    if direction == -1:
        return -1.0, sec_r
    return sec_f, sec_r


def _mode_costs(tags: TagList, highway: str, length_m: float, settings: GeoSettings) -> _ModeCosts:
    """Стоимости четырёх режимов ребра из OSM-тегов.

    bike/scooter — гибридные: едут и по проезжей части (кроме motor-классов
    без ``bicycle=yes``), и по path/footway/steps — dijkstra выбирает самое
    быстрое; пробок у них нет. ``bicycle=dismount`` — спешивание: ребро
    проходимо со скоростью пешехода. ``oneway`` связывает car всегда, лёгкие
    — если не отменён ``oneway:bicycle=no``/встречной велополосой, пешехода —
    только на path-классах или при явном ``oneway:foot``.
    """
    out = _ModeCosts()
    motor_default = highway not in _MOTOR_ONLY and tags.get("motorroad") != "yes"

    oneway_tag = tags.get("oneway")
    mv_dir = 1 if oneway_tag in _ONEWAY_YES else (-1 if oneway_tag == "-1" else 0)
    if mv_dir == 0 and tags.get("junction") == "roundabout":
        mv_dir = 1

    # car: моторный граф; vehicle=no/private режет без явного motor_vehicle.
    car_kmh = settings.car_speeds.get(highway)
    vehicle_deny = (
        tags.get("vehicle") in _ACCESS_DENY
        and tags.get("motor_vehicle") not in _ACCESS_ALLOW
        and tags.get("motorcar") not in _ACCESS_ALLOW
    )
    car_allowed = (
        car_kmh is not None
        and not vehicle_deny
        and _access_allowed(tags, "motor_vehicle", True)
        and tags.get("motorcar") not in _ACCESS_DENY
    )
    car_dir = _dir_override(tags.get("oneway:motor_vehicle"), mv_dir)
    # maxspeed — легальный потолок: только понижает скорость класса;
    # maxspeed:forward/backward задают лимит по направлению ребра.
    ms = _maxspeed_kmh(tags.get("maxspeed"))
    ms_f_raw = _maxspeed_kmh(tags.get("maxspeed:forward"))
    ms_r_raw = _maxspeed_kmh(tags.get("maxspeed:backward"))
    ms_f = ms_f_raw if ms_f_raw is not None else ms
    ms_r = ms_r_raw if ms_r_raw is not None else ms
    if car_allowed and car_kmh is not None:
        fwd = min(car_kmh, ms_f) if ms_f is not None else car_kmh
        rev = min(car_kmh, ms_r) if ms_r is not None else car_kmh
        out.car = _pair_dirs(length_m, fwd, rev, car_dir)
    else:
        out.car = _pair(length_m, None, car_dir)

    # foot: всё кроме motor-классов/motorroad без foot=yes.
    foot_allowed = _access_allowed(tags, "foot", motor_default)
    foot_kmh = settings.foot_speed_overrides.get(highway, settings.foot_speed_kmh)
    foot_dir = _dir_override(
        tags.get("oneway:foot"), mv_dir if highway in _PATH_CLASSES else 0
    )
    out.foot = _pair(length_m, foot_kmh if foot_allowed else None, foot_dir)

    # bike/scooter: гибрид дороги и пеших путей.
    light_default = motor_default and _access_allowed(tags, "bicycle", True)
    dismount = tags.get("bicycle") == "dismount"
    ob = tags.get("oneway:bicycle")
    if ob is not None:
        light_dir = _dir_override(ob, 0)
    elif _has_opposite_cycleway(tags):
        light_dir = 0
    else:
        light_dir = mv_dir
    for mode, speeds, fb_key in (
        ("bike", settings.bike_speeds, "bike"),
        ("scooter", settings.scooter_speeds, "scooter"),
    ):
        allowed = light_default
        kmh: float | None = speeds.get(highway)
        if kmh is None and allowed:
            fb = settings.light_path_fallback_kmh if highway in _PATH_CLASSES else settings.light_road_fallback_kmh
            kmh = float(fb.get(fb_key, 0))
        if dismount and allowed:
            kmh = settings.foot_speed_kmh
        pair = _pair(length_m, kmh if allowed else None, light_dir)
        if mode == "bike":
            out.bike = pair
        else:
            out.scooter = pair
    return out


class _RegionCountRow(BaseModel):
    entity: str
    region: str
    c: int


class _RowBuilder:
    """Строки БД из объектов OSM без накопления: каждый вызов возвращает список.

    Потребление памяти парсинга ограничено буферами caller'а: строки сливаются
    в Postgres батчами по ходу чтения экстракта, а локации нод лежат в
    дисковом индексе ``sparse_file_array`` — Python-структур на десятки
    миллионов записей не создаётся. Один builder — один регион: bbox и
    ``region``-тег строк берутся из записи ``geo_regions``.
    """

    def __init__(
        self,
        settings: GeoSettings,
        *,
        bbox: tuple[float, float, float, float],
        region: str,
    ) -> None:
        self._bbox: tuple[float, float, float, float] = bbox
        self._region: str = region
        self._settings: GeoSettings = settings

    def _in_bbox(self, lat: float, lng: float) -> bool:
        lat_min, lng_min, lat_max, lng_max = self._bbox
        return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max

    def node_row(self, n: Node) -> dict[str, SqlParameterValue] | None:
        if not n.location.valid() or not self._in_bbox(n.location.lat, n.location.lon):
            return None
        if not n.tags.get("addr:housenumber"):
            return None
        name = _display_name(n.tags)
        if not name:
            return None
        return {
            "osm_type": "node",
            "osm_id": n.id,
            "display_name": name,
            "city": n.tags.get("addr:city") or n.tags.get("addr:place") or "",
            "street": n.tags.get("addr:street") or "",
            "housenumber": n.tags.get("addr:housenumber") or "",
            "postcode": n.tags.get("addr:postcode") or "",
            "lat": n.location.lat,
            "lng": n.location.lon,
            "region": self._region,
        }

    def barrier_row(self, n: Node) -> dict[str, SqlParameterValue] | None:
        """Строка барьера из ноды ``barrier=*``; без тега/вне bbox — ``None``."""
        barrier = n.tags.get("barrier")
        if not barrier:
            return None
        if not n.location.valid() or not self._in_bbox(n.location.lat, n.location.lon):
            return None
        car, foot, bike, scooter = _barrier_blocks(n.tags, barrier)
        return {
            "osm_node_id": n.id,
            "barrier": barrier[:64],
            "block_car": car,
            "block_foot": foot,
            "block_bike": bike,
            "block_scooter": scooter,
            "lat": n.location.lat,
            "lng": n.location.lon,
            "region": self._region,
        }

    def signal_row(self, n: Node) -> dict[str, SqlParameterValue] | None:
        """Строка светофора из ноды ``highway=traffic_signals``."""
        if n.tags.get("highway") != "traffic_signals":
            return None
        if not n.location.valid() or not self._in_bbox(n.location.lat, n.location.lon):
            return None
        return {
            "osm_node_id": n.id,
            "lat": n.location.lat,
            "lng": n.location.lon,
            "region": self._region,
        }

    def _coord(self, n: NodeRef) -> tuple[float, float] | None:
        if n.location.valid() and self._in_bbox(n.location.lat, n.location.lon):
            return (n.location.lat, n.location.lon)
        return None

    def way_rows(
        self, w: Way
    ) -> tuple[
        dict[str, SqlParameterValue] | None,
        list[dict[str, SqlParameterValue]],
        list[tuple[int, float, float, str]],
    ]:
        """Адресная строка, рёбра графа и вершины одного way."""
        tags = w.tags
        coords = [self._coord(n) for n in w.nodes]

        addr_row: dict[str, SqlParameterValue] | None = None
        housenumber = tags.get("addr:housenumber")
        if housenumber:
            known = [c for c in coords if c is not None]
            if known:
                name = _display_name(tags)
                if name:
                    clat = sum(c[0] for c in known) / len(known)
                    clng = sum(c[1] for c in known) / len(known)
                    addr_row = {
                        "osm_type": "way",
                        "osm_id": w.id,
                        "display_name": name,
                        "city": tags.get("addr:city") or tags.get("addr:place") or "",
                        "street": tags.get("addr:street") or "",
                        "housenumber": housenumber,
                        "postcode": tags.get("addr:postcode") or "",
                        "lat": clat,
                        "lng": clng,
                        "region": self._region,
                    }

        edge_rows: list[dict[str, SqlParameterValue]] = []
        vertex_rows: list[tuple[int, float, float, str]] = []
        highway = tags.get("highway")
        if not highway or highway in _HIGHWAY_SKIP:
            return addr_row, edge_rows, vertex_rows
        name = tags.get("name", "")
        oneway_tag = tags.get("oneway", "")
        oneway = 1 if oneway_tag in _ONEWAY_YES else (-1 if oneway_tag == "-1" else 0)

        for i in range(len(w.nodes) - 1):
            a = coords[i]
            b = coords[i + 1]
            if a is None or b is None or a == b:
                continue
            length_m = _haversine_m(a[0], a[1], b[0], b[1])
            costs = _mode_costs(tags, highway, length_m, self._settings)
            if not costs.any_passable():
                continue
            vertex_rows.append((w.nodes[i].ref, a[0], a[1], self._region))
            vertex_rows.append((w.nodes[i + 1].ref, b[0], b[1], self._region))
            edge_rows.append(
                {
                    "source": w.nodes[i].ref,
                    "target": w.nodes[i + 1].ref,
                    "src_lat": a[0],
                    "src_lng": a[1],
                    "dst_lat": b[0],
                    "dst_lng": b[1],
                    "length_m": length_m,
                    "car_cost": costs.car[0],
                    "car_reverse_cost": costs.car[1],
                    "foot_cost": costs.foot[0],
                    "foot_reverse_cost": costs.foot[1],
                    "bike_cost": costs.bike[0],
                    "bike_reverse_cost": costs.bike[1],
                    "scooter_cost": costs.scooter[0],
                    "scooter_reverse_cost": costs.scooter[1],
                    "oneway": oneway,
                    "highway": highway,
                    "name": name,
                    "osm_way_id": w.id,
                    "region": self._region,
                }
            )
        return addr_row, edge_rows, vertex_rows

    def relation_row(
        self, r: Relation
    ) -> dict[str, SqlParameterValue] | None:
        """Строка запрета поворота из ``type=restriction``.

        Берутся сырые ссылки членов: ровно один ``from``-way, один
        ``to``-way и ``via`` — node либо way (через-way магистралей
        резолва в узел нет, но строка сохраняется для слоя). Тип поворота
        (left/right/straight/u) хранится как есть — роутингу важен лишь
        префикс ``no_``/``only_``/``no_entry``/``no_exit``.
        """
        if r.tags.get("type") != "restriction":
            return None
        restriction = r.tags.get("restriction")
        if not restriction:
            return None
        from_way: int | None = None
        to_way: int | None = None
        via_node: int | None = None
        via_way: int | None = None
        for m in r.members:
            if m.role == "from" and m.type == "w":
                from_way = m.ref
            elif m.role == "to" and m.type == "w":
                to_way = m.ref
            elif m.role == "via" and m.type == "n":
                via_node = m.ref
            elif m.role == "via" and m.type == "w" and via_way is None:
                via_way = m.ref
        if from_way is None or to_way is None:
            return None
        if via_node is None and via_way is None:
            return None
        return {
            "osm_relation_id": r.id,
            "restriction": restriction[:64],
            "from_way": from_way,
            "to_way": to_way,
            "via_node": via_node,
            "via_way": via_way,
            "region": self._region,
        }


class OsmImportService:
    """Загрузка, парсинг и атомарная публикация поколений OSM-данных."""

    def __init__(
        self, settings: GeoSettings, coverage_service: GeoCoverageService
    ) -> None:
        self._settings: GeoSettings = settings
        self._coverage: GeoCoverageService = coverage_service

    async def run_sync(self) -> dict[str, SqlParameterValue]:
        """Полный цикл синхронизации; идемпотентен по Last-Modified.

        Session advisory lock сериализует конкурентные тики (cron,
        bootstrap, ручной enqueue): импортер один на кластер, повторный
        тик завершается skip — без дублей поколения.
        """
        _ = await self._ensure_state()
        if not self._settings.sync_enabled:
            return {"skipped": True, "reason": "sync_disabled"}
        async with geo_import_lock(self._settings.database.geo_url) as acquired:
            if not acquired:
                return {"skipped": True, "reason": "import_in_progress"}
            await self._coverage.ensure_seeded()
            return await self._run_locked()

    async def _run_locked(self) -> dict[str, SqlParameterValue]:
        """Тело синка под advisory lock; state перечитывается свежим."""
        state = await self._ensure_state()

        state.status = GeoImportStatus.DOWNLOADING
        state.started_at = datetime.now(UTC)
        state.updated_at = datetime.now(UTC)
        _ = await state.save()

        regions = await GeoRegion.list_enabled_by_name_asc()
        if not regions:
            state.status = GeoImportStatus.IDLE
            state.updated_at = datetime.now(UTC)
            _ = await state.save()
            return {"skipped": True, "reason": "no_regions"}

        try:
            downloaded = await self._download_if_newer(state, regions)
            if downloaded is None:
                state.status = GeoImportStatus.IDLE
                state.updated_at = datetime.now(UTC)
                _ = await state.save()
                return {"skipped": True, "reason": "not_modified"}
            bundles, cleanup_paths, source_modified = downloaded
            try:
                counts = await self._import(
                    bundles, generation=state.current_generation + 1
                )
            finally:
                for p in cleanup_paths:
                    Path(p).unlink(missing_ok=True)
            await self._publish(state, source_modified, counts, regions)
            totals = counts["totals"]
            return {
                "imported": True,
                "rows_addresses": totals.get("addresses", 0),
                "rows_vertices": totals.get("vertices", 0),
                "rows_edges": totals.get("edges", 0),
                "rows_restrictions": totals.get("restrictions", 0),
                "rows_barriers": totals.get("barriers", 0),
                "rows_signals": totals.get("signals", 0),
            }
        except Exception as exc:
            state.status = GeoImportStatus.FAILED
            state.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            state.updated_at = datetime.now(UTC)
            _ = await state.save()
            raise

    async def ensure_bootstrapped(self) -> bool:
        """Пустой справочник → синк ставится сразу, без ожидания cron-тика.

        Старт geo_worker: поколения ещё нет — ``GEO_OSM_SYNC_TICK`` уходит в
        очередь немедленно (первый импорт региона не ждёт расписание);
        данные есть — no-op, дальше работает регулярный тик scheduler.
        Повторный вызов безопасен: лишний тик завершится ``not_modified``.
        """
        if not self._settings.sync_enabled or not self._settings.osm_extract_urls:
            return False
        state = await self._ensure_state()
        if state.current_generation > 0:
            return False
        _ = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
        logger.info("geo.import.bootstrap_enqueued")
        return True

    async def _ensure_state(self) -> GeoImportState:
        state = await GeoImportState.get_state()
        if state is None:
            state = GeoImportState(id=1, updated_at=datetime.now(UTC))
            _ = await GeoImportState.objects.create(instance=state)
        return state

    async def _download_if_newer(
        self, state: GeoImportState, regions: list[GeoRegion]
    ) -> tuple[list[tuple[GeoRegion, list[str]]], list[str], datetime | None] | None:
        """HEAD по экстрактам всех регионов; свежих нет → ``None``.

        Возвращает ``(bundles, cleanup_paths, newest)``: ``bundles`` — пары
        ``(region, [paths])``; ``cleanup_paths`` — только скачанные
        tmp-файлы; ``file://``-источники не удаляются.
        """
        newest: datetime | None = None
        async with get_httpx_client(
            timeout=self._settings.osm_http_timeout_seconds
        ) as client:
            for region in regions:
                for url in region.extract_urls:
                    if url.startswith("file://"):
                        mtime = Path(url.removeprefix("file://")).stat().st_mtime
                        modified = datetime.fromtimestamp(mtime, UTC)
                    else:
                        head = await client.request(
                            "HEAD", url, follow_redirects=True
                        )
                        _ = head.raise_for_status()
                        lm = head.headers.get("last-modified")
                        modified = (
                            datetime.strptime(
                                lm, "%a, %d %b %Y %H:%M:%S %Z"
                            ).replace(tzinfo=UTC)
                            if lm
                            else datetime.now(UTC)
                        )
                    if newest is None or modified > newest:
                        newest = modified
            if (
                state.source_modified_at is not None
                and newest is not None
                and newest <= state.source_modified_at
                and state.current_generation > 0
            ):
                return None

            bundles: list[tuple[GeoRegion, list[str]]] = []
            cleanup_paths: list[str] = []
            for region in regions:
                paths: list[str] = []
                for url in region.extract_urls:
                    if url.startswith("file://"):
                        paths.append(url.removeprefix("file://"))
                        continue
                    tmp_path: str | None = None
                    async with client.stream("GET", url, follow_redirects=True) as resp:
                        _ = resp.raise_for_status()
                        with tempfile.NamedTemporaryFile(
                            suffix=".osm.pbf", delete=False
                        ) as tmp:
                            tmp_path = tmp.name
                            async for chunk in resp.aiter_bytes(1 << 20):
                                _ = tmp.write(chunk)
                    assert tmp_path is not None
                    paths.append(tmp_path)
                    cleanup_paths.append(tmp_path)
                bundles.append((region, paths))
        return bundles, cleanup_paths, newest

    async def _import(
        self,
        bundles: list[tuple[GeoRegion, list[str]]],
        *,
        generation: int,
    ) -> dict[str, dict[str, int]]:
        """Парсинг экстрактов регионов и заливка в новое поколение.

        Один проход ``FileProcessor`` на файл: объекты превращаются в строки и
        сливаются в Postgres по достижении ``import_batch_size``, локации нод —
        дисковый индекс ``sparse_file_array``. Память не зависит от размера
        экстракта: в куче живёт только три буфера <= размера батча; ``region``
        строк берётся из записи ``geo_regions``, bbox фильтрации — тоже.
        """
        state = await GeoImportState.get_state()
        assert state is not None
        state.status = GeoImportStatus.IMPORTING
        state.updated_at = datetime.now(UTC)
        _ = await state.save()

        bs = self._settings.import_batch_size
        addresses: list[dict[str, SqlParameterValue]] = []
        edges: list[dict[str, SqlParameterValue]] = []
        vertices: list[tuple[int, float, float, str]] = []
        restrictions: list[dict[str, SqlParameterValue]] = []
        barriers: list[dict[str, SqlParameterValue]] = []
        signals: list[dict[str, SqlParameterValue]] = []
        for region, paths in bundles:
            builder = _RowBuilder(
                self._settings, bbox=region.bbox_tuple(), region=region.name
            )
            for p in paths:
                fp = osmium.FileProcessor(p, _ENTITY_BITS).with_locations(
                    "sparse_file_array"
                )
                for obj in fp:
                    if isinstance(obj, Node):
                        row = builder.node_row(obj)
                        if row is not None:
                            addresses.append(row)
                        b_row = builder.barrier_row(obj)
                        if b_row is not None:
                            barriers.append(b_row)
                        s_row = builder.signal_row(obj)
                        if s_row is not None:
                            signals.append(s_row)
                    elif isinstance(obj, Way):
                        addr_row, edge_rows, vertex_rows = builder.way_rows(obj)
                        if addr_row is not None:
                            addresses.append(addr_row)
                        edges.extend(edge_rows)
                        vertices.extend(vertex_rows)
                    elif isinstance(obj, Relation):
                        rel_row = builder.relation_row(obj)
                        if rel_row is not None:
                            restrictions.append(rel_row)
                    if len(addresses) >= bs:
                        await self._bulk_insert_addresses(addresses, generation)
                        addresses.clear()
                    if len(vertices) >= bs:
                        await self._bulk_insert_vertices(vertices, generation)
                        vertices.clear()
                    if len(edges) >= bs:
                        await self._bulk_insert_edges(edges, generation)
                        edges.clear()
                    if len(restrictions) >= bs:
                        await self._bulk_insert_restrictions(
                            restrictions, generation
                        )
                        restrictions.clear()
                    if len(barriers) >= bs:
                        await self._bulk_insert_barriers(barriers, generation)
                        barriers.clear()
                    if len(signals) >= bs:
                        await self._bulk_insert_signals(signals, generation)
                        signals.clear()

        await self._bulk_insert_addresses(addresses, generation)
        await self._bulk_insert_vertices(vertices, generation)
        await self._bulk_insert_edges(edges, generation)
        await self._bulk_insert_restrictions(restrictions, generation)
        await self._bulk_insert_barriers(barriers, generation)
        await self._bulk_insert_signals(signals, generation)
        await self._resolve_restriction_coords(generation)
        await self._apply_overlays(generation)
        return await self._generation_counts(generation)

    async def _bulk_insert_addresses(
        self, rows: list[dict[str, SqlParameterValue]], generation: int
    ) -> None:
        # bind-лимит Postgres 65535 — пачка ограничена ~5K строк по 12 колонок
        cols = 12
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for r in chunk:
                params.extend(
                    [
                        r["osm_type"], r["osm_id"], r["display_name"], r["city"],
                        r["street"], r["housenumber"], r["postcode"], r["lat"],
                        r["lng"], r["region"], generation, datetime.now(UTC),
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_addresses
                    (osm_type, osm_id, display_name, city, street, housenumber,
                     postcode, lat, lng, region, generation, created_at)
                VALUES {values}
                ON CONFLICT (osm_type, osm_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_vertices(
        self,
        vertices: list[tuple[int, float, float, str]],
        generation: int,
    ) -> None:
        cols = 5
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(vertices), bs):
            chunk = vertices[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for vid, lat, lng, region in chunk:
                params.extend([vid, lat, lng, region, generation])
            _ = await execute_raw(
                f"""
                INSERT INTO geo_road_vertices (node_id, lat, lng, region, generation)
                VALUES {values}
                ON CONFLICT (node_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_edges(
        self, rows: list[dict[str, SqlParameterValue]], generation: int
    ) -> None:
        cols = 21
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for r in chunk:
                params.extend(
                    [
                        r["source"], r["target"], r["src_lat"], r["src_lng"],
                        r["dst_lat"], r["dst_lng"], r["length_m"], r["car_cost"],
                        r["car_reverse_cost"], r["foot_cost"], r["foot_reverse_cost"],
                        r["bike_cost"], r["bike_reverse_cost"],
                        r["scooter_cost"], r["scooter_reverse_cost"],
                        r["oneway"], r["highway"], r["name"], r["osm_way_id"],
                        r["region"], generation,
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_road_edges
                    (source, target, src_lat, src_lng, dst_lat, dst_lng,
                     length_m, car_cost, car_reverse_cost, foot_cost,
                     foot_reverse_cost, bike_cost, bike_reverse_cost,
                     scooter_cost, scooter_reverse_cost,
                     oneway, highway, name, osm_way_id, region, generation)
                VALUES {values}
                ON CONFLICT (generation, osm_way_id, source, target) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_restrictions(
        self, rows: list[dict[str, SqlParameterValue]], generation: int
    ) -> None:
        cols = 9
        # Nullable-колонки: None-бинд execute_raw не выводит тип — явный каст.
        casts = ["", "", "", "", "::bigint", "::bigint", "", "", ""]
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "("
                + ",".join(
                    f"${j * cols + k}{casts[k - 1]}" for k in range(1, cols + 1)
                )
                + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for r in chunk:
                params.extend(
                    [
                        r["osm_relation_id"], r["restriction"], r["from_way"],
                        r["to_way"], r["via_node"], r["via_way"], r["region"],
                        generation, datetime.now(UTC),
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_turn_restrictions
                    (osm_relation_id, restriction, from_way, to_way,
                     via_node, via_way, region, generation, created_at)
                VALUES {values}
                ON CONFLICT (osm_relation_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_barriers(
        self, rows: list[dict[str, SqlParameterValue]], generation: int
    ) -> None:
        cols = 11
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for r in chunk:
                params.extend(
                    [
                        r["osm_node_id"], r["barrier"], r["block_car"],
                        r["block_foot"], r["block_bike"], r["block_scooter"],
                        r["lat"], r["lng"], r["region"],
                        generation, datetime.now(UTC),
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_barriers
                    (osm_node_id, barrier, block_car, block_foot,
                     block_bike, block_scooter, lat, lng, region,
                     generation, created_at)
                VALUES {values}
                ON CONFLICT (osm_node_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_signals(
        self, rows: list[dict[str, SqlParameterValue]], generation: int
    ) -> None:
        cols = 6
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for r in chunk:
                params.extend(
                    [
                        r["osm_node_id"], r["lat"], r["lng"], r["region"],
                        generation, datetime.now(UTC),
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_traffic_signals
                    (osm_node_id, lat, lng, region, generation, created_at)
                VALUES {values}
                ON CONFLICT (osm_node_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _resolve_restriction_coords(self, generation: int) -> None:
        """Координаты ``via``-узлов из вершин поколения — geom для слоя."""
        _ = await execute_raw(
            """
            UPDATE geo_turn_restrictions r
            SET via_lat = v.lat, via_lng = v.lng
            FROM geo_road_vertices v
            WHERE r.generation = $1 AND v.generation = $1
              AND v.node_id = r.via_node
            """,
            [generation],
            using="geo",
        )

    async def _apply_overlays(self, generation: int) -> None:
        """Перенос вечных оверлеев на новое поколение.

        Порядок детерминирован: enrich-атрибуты источников → патч админа
        (побеждает всегда) → тумбстоуны (удаление) → закрытия дорог.
        Строки generation=0 (manual) сюда не входят — они не поколение.
        """
        _ = await execute_raw(
            """
            UPDATE geo_addresses a
            SET gar_guid = e.gar_guid,
                canonical_name = e.canonical_name,
                cadastral_number = e.cadastral_number
            FROM geo_address_enrich e
            WHERE a.generation = $1
              AND a.osm_type = e.osm_type AND a.osm_id = e.osm_id
            """,
            [generation],
            using="geo",
        )
        _ = await execute_raw(
            """
            UPDATE geo_addresses a
            SET display_name = COALESCE(o.display_name, a.display_name),
                city = COALESCE(o.city, a.city),
                street = COALESCE(o.street, a.street),
                housenumber = COALESCE(o.housenumber, a.housenumber),
                postcode = COALESCE(o.postcode, a.postcode),
                lat = COALESCE(o.lat, a.lat),
                lng = COALESCE(o.lng, a.lng)
            FROM geo_address_overrides o
            WHERE a.generation = $1
              AND a.osm_type = o.osm_type AND a.osm_id = o.osm_id
              AND NOT o.suppressed
            """,
            [generation],
            using="geo",
        )
        _ = await execute_raw(
            """
            DELETE FROM geo_addresses a
            USING geo_address_overrides o
            WHERE a.generation = $1
              AND a.osm_type = o.osm_type AND a.osm_id = o.osm_id
              AND o.suppressed
            """,
            [generation],
            using="geo",
        )
        for entity, table, key_col in (
            ("barrier", "geo_barriers", "osm_node_id"),
            ("signal", "geo_traffic_signals", "osm_node_id"),
            ("restriction", "geo_turn_restrictions", "osm_relation_id"),
            ("edge", "geo_road_edges", "osm_way_id"),
        ):
            _ = await execute_raw(
                f"""
                DELETE FROM {table} x
                USING geo_suppressions s
                WHERE x.generation = $1
                  AND s.entity = $2 AND x.{key_col} = s.osm_id
                """,
                [generation, entity],
                using="geo",
            )
        for mode in ("car", "foot", "bike", "scooter"):
            _ = await execute_raw(
                f"""
                UPDATE geo_road_edges e
                SET {mode}_cost = -1, {mode}_reverse_cost = -1
                FROM geo_edge_overrides o
                WHERE e.generation = $1
                  AND e.osm_way_id = o.osm_way_id
                  AND COALESCE((o.cost_masks->>'{mode}')::boolean, false)
                """,
                [generation],
                using="geo",
            )

    async def _generation_counts(
        self, generation: int
    ) -> dict[str, dict[str, int]]:
        """Счётчики поколения после ON CONFLICT-дедупа: per-регион + totals."""
        rows = await execute_raw(
            """
            SELECT 'addresses' AS entity, region, count(*)::bigint AS c
            FROM geo_addresses WHERE generation=$1 GROUP BY region
            UNION ALL
            SELECT 'vertices', region, count(*)::bigint
            FROM geo_road_vertices WHERE generation=$1 GROUP BY region
            UNION ALL
            SELECT 'edges', region, count(*)::bigint
            FROM geo_road_edges WHERE generation=$1 GROUP BY region
            UNION ALL
            SELECT 'restrictions', region, count(*)::bigint
            FROM geo_turn_restrictions WHERE generation=$1 GROUP BY region
            UNION ALL
            SELECT 'barriers', region, count(*)::bigint
            FROM geo_barriers WHERE generation=$1 GROUP BY region
            UNION ALL
            SELECT 'signals', region, count(*)::bigint
            FROM geo_traffic_signals WHERE generation=$1 GROUP BY region
            """,
            [generation],
            using="geo",
        )
        per_region: dict[str, int] = {}
        totals: dict[str, int] = {}
        for r in rows:
            row = _RegionCountRow.model_validate(r)
            per_region[f"{row.entity}:{row.region}"] = row.c
            totals[row.entity] = totals.get(row.entity, 0) + row.c
        return {"per_region": per_region, "totals": totals}

    async def _publish(
        self,
        state: GeoImportState,
        source_modified: datetime | None,
        counts: dict[str, dict[str, int]],
        regions: list[GeoRegion],
    ) -> None:
        """Атомарный своп поколения + счётчики покрытия + очистка старого."""
        new_gen = state.current_generation + 1
        state.current_generation = new_gen
        state.status = GeoImportStatus.IDLE
        state.source_name = "osm"
        state.source_modified_at = source_modified
        totals = counts["totals"]
        state.rows_addresses = totals.get("addresses", 0)
        state.rows_vertices = totals.get("vertices", 0)
        state.rows_edges = totals.get("edges", 0)
        state.rows_restrictions = totals.get("restrictions", 0)
        state.rows_barriers = totals.get("barriers", 0)
        state.rows_signals = totals.get("signals", 0)
        state.last_error = ""
        now = datetime.now(UTC)
        state.finished_at = now
        state.updated_at = now
        _ = await state.save()
        # Счётчики покрытия активного поколения — по региону и сущности.
        per_region = counts["per_region"]
        for region in regions:
            for entity in (
                "addresses", "vertices", "edges",
                "restrictions", "barriers", "signals",
            ):
                await GeoStats.set_rows(
                    generation=new_gen,
                    source="osm",
                    region=region.name,
                    entity=entity,
                    rows=per_region.get(f"{entity}:{region.name}", 0),
                )
        await GeoRegion.mark_imported([r.name for r in regions])
        # Чистка старых поколений — после свопа, батчами; generation=0 —
        # вечнозелёные строки (manual), чистка их не трогает.
        for table in (
            "geo_addresses",
            "geo_road_vertices",
            "geo_road_edges",
            "geo_turn_restrictions",
            "geo_barriers",
            "geo_traffic_signals",
            "geo_stats",
        ):
            _ = await execute_raw(
                f"DELETE FROM {table} WHERE generation < $1 AND generation > 0",
                [new_gen],
                using="geo",
            )
        logger.info(
            "geo.import.published",
            generation=new_gen,
            **totals,
        )

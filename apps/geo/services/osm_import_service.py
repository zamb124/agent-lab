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
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.http import get_httpx_client
from core.logging import get_logger
from core.tasks import enqueue

if TYPE_CHECKING:
    from osmium.osm import Node, TagList, Way

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
    out.car = _pair(length_m, car_kmh if car_allowed else None, car_dir)

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


class _NeededNodesHandler(osmium.SimpleHandler):
    """Проход 1: id нод, нужных ways-адресам и ways-дорогам."""

    def __init__(self) -> None:
        super().__init__()
        self.needed: set[int] = set()

    def way(self, w: Way) -> None:
        if w.tags.get("addr:housenumber") or w.tags.get("highway"):
            self.needed.update(n.ref for n in w.nodes)


class _NodeLocationsHandler(osmium.SimpleHandler):
    """Проход 2: локации только нужных нод + узлы-адреса напрямую."""

    def __init__(self, needed: set[int], bbox: tuple[float, float, float, float]) -> None:
        super().__init__()
        self._needed: set[int] = needed
        self._bbox: tuple[float, float, float, float] = bbox
        self.locations: dict[int, tuple[float, float]] = {}
        self.node_addresses: list[dict[str, object]] = []

    def node(self, n: Node) -> None:
        if not n.location.valid():
            return
        lat_min, lng_min, lat_max, lng_max = self._bbox
        if not (lat_min <= n.location.lat <= lat_max and lng_min <= n.location.lon <= lng_max):
            return
        if n.id in self._needed:
            self.locations[n.id] = (n.location.lat, n.location.lon)
        if n.tags.get("addr:housenumber"):
            name = _display_name(n.tags)
            if name:
                self.node_addresses.append(
                    {
                        "osm_type": "node",
                        "osm_id": n.id,
                        "display_name": name,
                        "city": n.tags.get("addr:city") or n.tags.get("addr:place") or "",
                        "street": n.tags.get("addr:street") or "",
                        "housenumber": n.tags.get("addr:housenumber") or "",
                        "postcode": n.tags.get("addr:postcode") or "",
                        "lat": n.location.lat,
                        "lng": n.location.lon,
                    }
                )


class _WaysHandler(osmium.SimpleHandler):
    """Проход 3: ways → адреса (центроид) и рёбра дорожного графа."""

    def __init__(
        self,
        locations: dict[int, tuple[float, float]],
        settings: GeoSettings,
    ) -> None:
        super().__init__()
        self._loc: dict[int, tuple[float, float]] = locations
        self._settings: GeoSettings = settings
        self.way_addresses: list[dict[str, object]] = []
        self.edges: list[dict[str, object]] = []
        self.vertex_ids: set[int] = set()

    def way(self, w: Way) -> None:
        tags = w.tags
        coords = [self._loc.get(n.ref) for n in w.nodes]

        housenumber = tags.get("addr:housenumber")
        if housenumber:
            known = [c for c in coords if c is not None]
            if known:
                name = _display_name(tags)
                if name:
                    clat = sum(c[0] for c in known) / len(known)
                    clng = sum(c[1] for c in known) / len(known)
                    self.way_addresses.append(
                        {
                            "osm_type": "way",
                            "osm_id": w.id,
                            "display_name": name,
                            "city": tags.get("addr:city") or tags.get("addr:place") or "",
                            "street": tags.get("addr:street") or "",
                            "housenumber": housenumber,
                            "postcode": tags.get("addr:postcode") or "",
                            "lat": clat,
                            "lng": clng,
                        }
                    )

        highway = tags.get("highway")
        if not highway or highway in _HIGHWAY_SKIP:
            return
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
            self.vertex_ids.update((w.nodes[i].ref, w.nodes[i + 1].ref))
            self.edges.append(
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
                }
            )


class OsmImportService:
    """Загрузка, парсинг и атомарная публикация поколений OSM-данных."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def run_sync(self) -> dict[str, object]:
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
            return await self._run_locked()

    async def _run_locked(self) -> dict[str, object]:
        """Тело синка под advisory lock; state перечитывается свежим."""
        state = await self._ensure_state()

        state.status = GeoImportStatus.DOWNLOADING
        state.started_at = datetime.now(UTC)
        state.updated_at = datetime.now(UTC)
        _ = await state.save()

        try:
            downloaded = await self._download_if_newer(state)
            if downloaded is None:
                state.status = GeoImportStatus.IDLE
                state.updated_at = datetime.now(UTC)
                _ = await state.save()
                return {"skipped": True, "reason": "not_modified"}
            paths, cleanup_paths, source_modified = downloaded
            try:
                counts = await self._import(paths, generation=state.current_generation + 1)
            finally:
                for p in cleanup_paths:
                    Path(p).unlink(missing_ok=True)
            await self._publish(state, source_modified, counts)
            return {"imported": True, **counts}
        except Exception as exc:
            state.status = GeoImportStatus.FAILED
            state.last_error = str(exc)[:2000]
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
        self, state: GeoImportState
    ) -> tuple[list[str], list[str], datetime | None] | None:
        """HEAD по всем экстрактам; свежих нет → ``None``.

        Возвращает ``(paths, cleanup_paths, newest)``: ``cleanup_paths`` —
        только скачанные tmp-файлы; ``file://``-источники не удаляются.
        """
        newest: datetime | None = None
        async with get_httpx_client(
            timeout=self._settings.osm_http_timeout_seconds
        ) as client:
            for url in self._settings.osm_extract_urls:
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

            paths: list[str] = []
            cleanup_paths: list[str] = []
            for url in self._settings.osm_extract_urls:
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
        return paths, cleanup_paths, newest

    async def _import(self, paths: list[str], *, generation: int) -> dict[str, int]:
        """Парсинг всех экстрактов и заливка в новое поколение."""
        state = await GeoImportState.get_state()
        assert state is not None
        state.status = GeoImportStatus.IMPORTING
        state.updated_at = datetime.now(UTC)
        _ = await state.save()

        needed: set[int] = set()
        for p in paths:
            h = _NeededNodesHandler()
            h.apply_file(p, locations=False)
            needed |= h.needed

        locations: dict[int, tuple[float, float]] = {}
        addresses: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        vertex_ids: set[int] = set()
        for p in paths:
            nh = _NodeLocationsHandler(needed, self._settings.coverage_bbox)
            nh.apply_file(p, locations=False)
            locations.update(nh.locations)
            addresses.extend(nh.node_addresses)
            wh = _WaysHandler(locations, self._settings)
            wh.apply_file(p, locations=False)
            addresses.extend(wh.way_addresses)
            edges.extend(wh.edges)
            vertex_ids |= wh.vertex_ids

        await self._bulk_insert_addresses(addresses, generation)
        await self._bulk_insert_vertices(locations, vertex_ids, generation)
        await self._bulk_insert_edges(edges, generation)
        return {
            "rows_addresses": len(addresses),
            "rows_vertices": len([v for v in vertex_ids if v in locations]),
            "rows_edges": len(edges),
        }

    async def _bulk_insert_addresses(
        self, rows: list[dict[str, object]], generation: int
    ) -> None:
        # bind-лимит Postgres 65535 — пачка ограничена ~5.4K строк по 11 колонок
        cols = 11
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[object] = []
            for r in chunk:
                params.extend(
                    [
                        r["osm_type"], r["osm_id"], r["display_name"], r["city"],
                        r["street"], r["housenumber"], r["postcode"], r["lat"],
                        r["lng"], generation, datetime.now(UTC),
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_addresses
                    (osm_type, osm_id, display_name, city, street, housenumber,
                     postcode, lat, lng, generation, created_at)
                VALUES {values}
                ON CONFLICT (osm_type, osm_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_vertices(
        self,
        locations: dict[int, tuple[float, float]],
        vertex_ids: set[int],
        generation: int,
    ) -> None:
        # Вершины без локации (нод вне bbox) пропускаем — рёбра к ним
        # просто не притянутся на snap.
        ids = sorted(v for v in vertex_ids if v in locations)
        cols = 4
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(ids), bs):
            chunk = ids[i : i + bs]
            values = ",".join(
                f"(${j * cols + 1},${j * cols + 2},${j * cols + 3},${j * cols + 4})"
                for j in range(len(chunk))
            )
            params: list[object] = []
            for vid in chunk:
                lat, lng = locations[vid]
                params.extend([vid, lat, lng, generation])
            _ = await execute_raw(
                f"""
                INSERT INTO geo_road_vertices (node_id, lat, lng, generation)
                VALUES {values}
                ON CONFLICT (node_id, generation) DO NOTHING
                """,
                params,
                using="geo",
            )

    async def _bulk_insert_edges(
        self, rows: list[dict[str, object]], generation: int
    ) -> None:
        cols = 20
        bs = min(self._settings.import_batch_size, 60_000 // cols)
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[object] = []
            for r in chunk:
                params.extend(
                    [
                        r["source"], r["target"], r["src_lat"], r["src_lng"],
                        r["dst_lat"], r["dst_lng"], r["length_m"], r["car_cost"],
                        r["car_reverse_cost"], r["foot_cost"], r["foot_reverse_cost"],
                        r["bike_cost"], r["bike_reverse_cost"],
                        r["scooter_cost"], r["scooter_reverse_cost"],
                        r["oneway"], r["highway"], r["name"], r["osm_way_id"],
                        generation,
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_road_edges
                    (source, target, src_lat, src_lng, dst_lat, dst_lng,
                     length_m, car_cost, car_reverse_cost, foot_cost,
                     foot_reverse_cost, bike_cost, bike_reverse_cost,
                     scooter_cost, scooter_reverse_cost,
                     oneway, highway, name, osm_way_id, generation)
                VALUES {values}
                """,
                params,
                using="geo",
            )

    async def _publish(
        self,
        state: GeoImportState,
        source_modified: datetime | None,
        counts: dict[str, int],
    ) -> None:
        """Атомарный своп поколения + очистка старого."""
        new_gen = state.current_generation + 1
        state.current_generation = new_gen
        state.status = GeoImportStatus.IDLE
        state.source_modified_at = source_modified
        state.rows_addresses = counts["rows_addresses"]
        state.rows_vertices = counts["rows_vertices"]
        state.rows_edges = counts["rows_edges"]
        state.last_error = ""
        now = datetime.now(UTC)
        state.finished_at = now
        state.updated_at = now
        _ = await state.save()
        # Чистка старых поколений — после свопа, батчами.
        for table in ("geo_addresses", "geo_road_vertices", "geo_road_edges"):
            _ = await execute_raw(
                f"DELETE FROM {table} WHERE generation < $1",
                [new_gen],
                using="geo",
            )
        logger.info(
            "geo.import.published",
            generation=new_gen,
            **counts,
        )

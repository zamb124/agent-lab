"""Импортёр Overture Maps Foundation (monthly release, parquet).

Релиз — partitioned parquet ``{release}/theme={theme}/type={type}/*.parquet``:
Azure-mirror ``overture_base_url`` (anonymous blob listing
``?restype=container&comp=list&prefix=``) либо ``file://`` каталог с той же
раскладкой (тестовая фикстура). Темы ``overture_themes``:

- ``addresses`` (type ``address``): точка + ``number``/``street``/``city``/
  ``postcode`` → **gap-fill** gen-0 ``geo_addresses`` ``osm_type='overture'``,
  отрицательный ``osm_id`` из ``geo_manual_id_seq``. Строка пропускается, если
  в радиусе ``overture_gap_radius_m`` уже есть адрес с тем же housenumber
  (``ST_DWithin`` по ``geom::geography``).
- ``buildings`` (type ``building``): WKB-полигон → ``geo_buildings`` upsert,
  ключ ``cadastral_number`` = GERS id (32 hex, уникален, форматно не
  пересекается с кадастровыми номерами Росреестра).

Курсор ``geo_source_cursors(source='overture', region)`` —
``release|theme|file_idx:rg_idx``: тик читает ``overture_tick_rowgroups``
row-groups и продолжает со следующего; смена релиза — проход заново.
Геометрия — WKB (ISO), разбирается встроенным минимальным парсером
(Point/Polygon/MultiPolygon, 2D/Z/M) без shapely.
"""

from __future__ import annotations

import json
import re
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol

import fsspec  # pyright: ignore[reportMissingTypeStubs] — пакет без stub-ов
import pyarrow.parquet as pq  # pyright: ignore[reportMissingTypeStubs] — пакет без stub-ов
from defusedxml import ElementTree as SafeET
from oxyde import execute_raw
from pydantic import BaseModel

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_building import GeoBuilding
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion
from apps.geo.models.geo_source import GeoSource
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from core.http import get_httpx_client
from core.imports import module_sdk
from core.logging import get_logger
from core.types import JsonObject, JsonValue, SqlParameterValue

_SOURCE = "overture"
_LOCK_KEY = "geo.overture_sync"
_BATCH_INSERT = 500

_logger = get_logger(__name__)

_THEME_TYPES: dict[str, str] = {
    "addresses": "address",
    "buildings": "building",
}
# Колонки темы: bbox-структура + геометрия + адресные атрибуты.
_THEME_COLUMNS: dict[str, list[str]] = {
    "addresses": ["id", "bbox", "geometry", "number", "street", "postcode", "city"],
    "buildings": ["id", "bbox", "geometry"],
}


class OvertureSyncResult(BaseModel):
    """Итог тика: ``skipped`` — причина пропуска, иначе по регионам."""

    skipped: str = ""
    regions: dict[str, JsonObject] = {}


class _RowBbox(BaseModel):
    """Структура ``bbox`` строки parquet: прямоугольник WGS84."""

    xmin: float
    xmax: float
    ymin: float
    ymax: float


class _AddressParquetRow(BaseModel):
    """Строка ``theme=addresses``: точка + атрибуты адреса."""

    id: str | None = None
    bbox: _RowBbox | None = None
    geometry: bytes | None = None
    number: str | None = None
    street: str | None = None
    postcode: str | None = None
    city: str | None = None


class _BuildingParquetRow(BaseModel):
    """Строка ``theme=buildings``: полигон + GERS id."""

    id: str | None = None
    bbox: _RowBbox | None = None
    geometry: bytes | None = None


# Protocol-обёртки untyped pyarrow/fsspec (как _CairoSvgModule в core).
class _ParquetTable(Protocol):
    def to_pylist(self) -> list[JsonObject]: ...


class _ParquetMeta(Protocol):
    num_row_groups: int


class _ParquetFile(Protocol):
    @property
    def metadata(self) -> _ParquetMeta | None: ...

    def read_row_group(
        self, i: int, columns: list[str] | None = None
    ) -> _ParquetTable: ...


class _ParquetModule(Protocol):
    def ParquetFile(self, path: str | BinaryIO) -> _ParquetFile: ...  # noqa: N802 — имя пакета


class _FsModule(Protocol):
    def open(self, path: str, mode: str) -> BinaryIO: ...


class _FsspecModule(Protocol):
    def get_fs_token_paths(
        self, url: str
    ) -> tuple[_FsModule, str, list[str]]: ...


_PQ = module_sdk(pq, _ParquetModule)
_FSSPEC = module_sdk(fsspec, _FsspecModule)


# ── WKB → geojson ─────────────────────────────────────────────────────────

_WKB_Z = 1000
_WKB_M = 2000
_WKB_EWKB_Z = 0x20000000
_WKB_EWKB_M = 0x40000000
_WKB_EWKB_SRID = 0x80000000


class _WkbReader:
    """Курсор по бинарному WKB (endianness — по первому байту каждого уровня)."""

    def __init__(self, data: bytes) -> None:
        self._buf: memoryview = memoryview(data)
        self._pos: int = 0
        self._end: str = "<"

    def _take(self, size: int) -> memoryview:
        chunk = self._buf[self._pos : self._pos + size]
        self._pos += size
        return chunk

    def _uint32(self) -> int:
        return int.from_bytes(
            self._take(4), "little" if self._end == "<" else "big"
        )

    def geom(self) -> JsonObject:
        order = self._take(1)[0]
        self._end = "<" if order == 1 else ">"
        raw_type = self._uint32()
        dims = 2
        if _WKB_EWKB_SRID & raw_type:
            _ = self._take(4)
        if raw_type & _WKB_EWKB_Z:
            dims += 1
        if raw_type & _WKB_EWKB_M:
            dims += 1
        base = raw_type & 0xFFFF
        if 1000 <= raw_type < _WKB_EWKB_Z:
            offset = raw_type // 1000
            dims += offset % 2 + (1 if offset >= 2 else 0)
            base = raw_type % 1000
        if base == 1:
            return {"type": "Point", "coordinates": self._point(dims)}
        if base == 3:
            return {"type": "Polygon", "coordinates": self._polygon(dims)}
        if base == 6:
            count = self._uint32()
            return {
                "type": "MultiPolygon",
                "coordinates": [self.geom()["coordinates"] for _ in range(count)],
            }
        raise ValueError(f"unsupported WKB type {raw_type}")

    def _point(self, dims: int) -> list[float]:
        values: tuple[float, ...] = struct.unpack(
            f"{self._end}{dims}d", self._take(8 * dims)
        )
        return [float(values[0]), float(values[1])]

    def _polygon(self, dims: int) -> list[list[list[float]]]:
        rings = self._uint32()
        return [
            [self._point(dims) for _ in range(self._uint32())]
            for _ in range(rings)
        ]


def _wkb_to_geojson(data: bytes) -> JsonObject:
    """WKB (ISO/EWKB) → GeoJSON geometry dict; Point/Polygon/MultiPolygon."""
    return _WkbReader(data).geom()


def _geojson_centroid(geojson: JsonObject) -> tuple[float, float] | None:
    """Центроид внешнего кольца Polygon/MultiPolygon → ``(lat, lng)``."""
    gtype = geojson.get("type")
    coords = geojson.get("coordinates")
    ring: JsonValue | None = None
    if gtype == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0]
    elif (
        gtype == "MultiPolygon"
        and isinstance(coords, list)
        and coords
        and isinstance(coords[0], list)
        and coords[0]
    ):
        ring = coords[0][0]
    points: list[tuple[float, float]] = []
    if isinstance(ring, list):
        points = [
            (float(str(p[0])), float(str(p[1])))
            for p in ring
            if isinstance(p, list) and len(p) >= 2
        ]
    if not points:
        return None
    lng = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lat, lng


# ── listing ────────────────────────────────────────────────────────────────


def _theme_dir(base: str, release: str, theme: str) -> str:
    return f"{base}/{release}/theme={theme}/type={_THEME_TYPES[theme]}"


def _list_local(theme_dir: str) -> list[str]:
    """``file://`` зеркало — файлы ``*.parquet`` каталога темы."""
    path = Path(theme_dir.removeprefix("file://"))
    if not path.is_dir():
        return []
    return sorted(str(item) for item in path.glob("*.parquet"))


async def _list_azure(
    base: str, release: str, theme: str, timeout: float
) -> list[str]:
    """Anonymous Azure blob listing контейнера релизов по prefix темы."""
    prefix = f"{release}/theme={theme}/type={_THEME_TYPES[theme]}/"
    names: list[str] = []
    marker = ""
    async with get_httpx_client(timeout=timeout) as client:
        while True:
            response = await client.get(
                base,
                params={
                    "restype": "container",
                    "comp": "list",
                    "prefix": prefix,
                    "marker": marker,
                },
            )
            _ = response.raise_for_status()
            root = SafeET.fromstring(response.content)
            for blob in root.iter():
                if blob.tag.endswith("Name") and blob.text:
                    names.append(f"{base}/{blob.text}")
            next_marker = ""
            for blob in root.iter():
                if blob.tag.endswith("NextMarker") and blob.text:
                    next_marker = blob.text
            if not next_marker:
                return sorted(names)
            marker = next_marker


# ── сервис ─────────────────────────────────────────────────────────────────


class OvertureImportService:
    """Месячный импорт релиза: row-group резюм → bbox-фильтр → gap-fill."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def run_sync(self) -> OvertureSyncResult:
        """Тик: ``overture_tick_rowgroups`` row-groups по каждому региону."""
        if not self._settings.overture_sync_enabled:
            return OvertureSyncResult(skipped="overture_sync_disabled")
        source = await GeoSource.by_name(_SOURCE)
        if source is not None and not source.enabled:
            return OvertureSyncResult(skipped="source_disabled")
        themes = [t for t in self._settings.overture_themes if t in _THEME_TYPES]
        if not themes:
            return OvertureSyncResult(skipped="no_themes")
        regions = await GeoRegion.list_enabled_by_name_asc()
        if not regions:
            return OvertureSyncResult(skipped="no_regions")
        async with geo_import_lock(
            self._settings.database.geo_url, key=_LOCK_KEY
        ) as acquired:
            if not acquired:
                return OvertureSyncResult(skipped="locked")
            generation = await GeoImportState.active_generation()
            regions_result: dict[str, JsonObject] = {}
            for region in regions:
                regions_result[region.name] = await self._sync_region(
                    region=region, themes=themes, generation=generation
                )
            return OvertureSyncResult(regions=regions_result)

    async def _sync_region(
        self,
        *,
        region: GeoRegion,
        themes: list[str],
        generation: int,
    ) -> JsonObject:
        """Row-groups региона с resume-курсором ``release|theme|file:rg``."""
        cursor = await GeoSourceCursor.by_source_region(_SOURCE, region.name)
        theme_idx, file_idx, rg_idx = self._parse_cursor(cursor)
        budget = self._settings.overture_tick_rowgroups
        processed = 0
        inserted = 0
        try:
            for ti in range(theme_idx, len(themes)):
                theme = themes[ti]
                files = await self._list_theme(theme)
                for fi in range(file_idx, len(files)):
                    pf = self._open_parquet(files[fi])
                    meta = pf.metadata
                    num_rgs = meta.num_row_groups if meta is not None else 0
                    for ri in range(rg_idx, num_rgs):
                        inserted += await self._apply_row_group(
                            pf=pf,
                            row_group=ri,
                            theme=theme,
                            region=region,
                            generation=generation,
                        )
                        processed += 1
                        rg_idx = ri + 1
                        if processed >= budget:
                            await self._save_cursor(
                                region=region.name,
                                theme_idx=ti,
                                file_idx=fi,
                                rg_idx=rg_idx,
                                status=GeoCursorStatus.RUNNING,
                            )
                            return {
                                "status": "running",
                                "row_groups": processed,
                                "inserted": inserted,
                            }
                    rg_idx = 0
                file_idx = 0
            await self._save_cursor(
                region=region.name,
                theme_idx=0,
                file_idx=0,
                rg_idx=0,
                status=GeoCursorStatus.DONE,
            )
            await self._flush_stats(region=region.name)
            return {
                "status": "done",
                "row_groups": processed,
                "inserted": inserted,
            }
        except Exception as exc:
            await GeoSourceCursor.mark_failed(
                source=_SOURCE,
                region=region.name,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _parse_cursor(
        self, cursor: GeoSourceCursor | None
    ) -> tuple[int, int, int]:
        """``(theme_idx, file_idx, rg_idx)``; смена релиза/DONE — с нуля."""
        if cursor is None or cursor.status == GeoCursorStatus.DONE:
            return 0, 0, 0
        match = re.fullmatch(
            rf"{re.escape(self._settings.overture_release)}\|(\d+)\|(\d+):(\d+)",
            cursor.cursor,
        )
        if not match:
            return 0, 0, 0
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    async def _save_cursor(
        self,
        *,
        region: str,
        theme_idx: int,
        file_idx: int,
        rg_idx: int,
        status: GeoCursorStatus,
    ) -> None:
        _ = await GeoSourceCursor.upsert_progress(
            source=_SOURCE,
            region=region,
            cursor=(
                f"{self._settings.overture_release}|"
                f"{theme_idx}|{file_idx}:{rg_idx}"
            ),
            rows_done=rg_idx,
            status=status,
        )

    async def _list_theme(self, theme: str) -> list[str]:
        base = self._settings.overture_base_url
        theme_dir = _theme_dir(base, self._settings.overture_release, theme)
        if base.startswith("file://"):
            return _list_local(theme_dir)
        return await _list_azure(
            base,
            self._settings.overture_release,
            theme,
            self._settings.overture_http_timeout_seconds,
        )

    def _open_parquet(self, path: str) -> _ParquetFile:
        if path.startswith("file://") or not path.startswith("http"):
            return _PQ.ParquetFile(path.removeprefix("file://"))
        fs, _, paths = _FSSPEC.get_fs_token_paths(path)
        return _PQ.ParquetFile(fs.open(paths[0], "rb"))

    async def _apply_row_group(
        self,
        *,
        pf: _ParquetFile,
        row_group: int,
        theme: str,
        region: GeoRegion,
        generation: int,
    ) -> int:
        """Row-group → bbox-фильтр → адресный gap-fill / здания."""
        columns = _THEME_COLUMNS[theme]
        table = pf.read_row_group(row_group, columns=columns)
        south, west, north, east = region.bbox_tuple()
        rows = table.to_pylist()
        inserted = 0
        if theme == "addresses":
            batch: list[SqlParameterValue] = []
            for raw in rows:
                row = _AddressParquetRow.model_validate(raw)
                if not row.bbox or not self._bbox_hits(
                    row.bbox, south, west, north, east
                ):
                    continue
                number = (row.number or "").strip()
                if not row.geometry or not number:
                    continue
                point = _wkb_to_geojson(row.geometry)
                coords = point.get("coordinates")
                if not isinstance(coords, list) or len(coords) < 2:
                    continue
                lng, lat = float(str(coords[0])), float(str(coords[1]))
                if await self._address_exists(
                    region=region.name,
                    generation=generation,
                    housenumber=number,
                    lng=lng,
                    lat=lat,
                ):
                    continue
                street = (row.street or "").strip()
                batch.extend(
                    [
                        f"{street}, {number}" if street else number,
                        row.city or "",
                        street,
                        number,
                        row.postcode or "",
                        lat,
                        lng,
                        region.name,
                        datetime.now(UTC),
                    ]
                )
                inserted += 1
                if len(batch) >= _BATCH_INSERT * 9:
                    await self._flush_addresses(batch)
                    batch = []
            if batch:
                await self._flush_addresses(batch)
        else:
            for raw in rows:
                row = _BuildingParquetRow.model_validate(raw)
                if not row.bbox or not self._bbox_hits(
                    row.bbox, south, west, north, east
                ):
                    continue
                gers = (row.id or "")[:32]
                if not row.geometry or not gers:
                    continue
                geojson = _wkb_to_geojson(row.geometry)
                centroid = _geojson_centroid(geojson)
                if centroid is None:
                    continue
                lat, lng = centroid
                _ = await GeoBuilding.upsert_by_cadastral_number(
                    GeoBuilding(
                        cadastral_number=gers,
                        address="",
                        lat=lat,
                        lng=lng,
                        geojson=json.dumps(geojson),
                        region=region.name,
                        source=_SOURCE,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                inserted += 1
        return inserted

    @staticmethod
    def _bbox_hits(
        bbox: _RowBbox, south: float, west: float, north: float, east: float
    ) -> bool:
        """Строка пересекает bbox региона (struct xmin/xmax/ymin/ymax)."""
        return not (
            bbox.xmin > east
            or bbox.xmax < west
            or bbox.ymin > north
            or bbox.ymax < south
        )

    async def _address_exists(
        self,
        *,
        region: str,
        generation: int,
        housenumber: str,
        lng: float,
        lat: float,
    ) -> bool:
        """Gap-fill дедуп: тот же housenumber в ``overture_gap_radius_m``."""
        rows: list[dict[str, SqlParameterValue]] = await execute_raw(
            """
            SELECT 1 FROM geo_addresses
            WHERE region = $1 AND generation IN (0, $2)
              AND lower(replace(housenumber, ' ', '')) = $3
              AND ST_DWithin(
                  geom::geography,
                  ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography,
                  $6)
            LIMIT 1
            """,
            [
                region,
                generation,
                housenumber.lower().replace(" ", ""),
                lng,
                lat,
                self._settings.overture_gap_radius_m,
            ],
            using="geo",
        )
        return bool(rows)

    async def _flush_addresses(self, batch: list[SqlParameterValue]) -> None:
        """Multirow INSERT gen-0 адресов ``osm_type='overture'``."""
        cols = 9
        placeholders = ", ".join(
            "('overture', -nextval('geo_manual_id_seq'), "
            + ", ".join(f"${i * cols + j}" for j in range(1, cols))
            + f", 0, 'overture', ${i * cols + cols})"
            for i in range(len(batch) // cols)
        )
        _ = await execute_raw(
            f"""
            INSERT INTO geo_addresses
                (osm_type, osm_id, display_name, city, street, housenumber,
                 postcode, lat, lng, region, generation, source, created_at)
            VALUES {placeholders}
            """,
            batch,
            using="geo",
        )

    async def _flush_stats(self, *, region: str) -> None:
        """Счётчики источника — честные COUNT(*) по вставленным строкам."""
        for entity, table, where in (
            (
                "addresses",
                "geo_addresses",
                "source = 'overture' AND region = $1",
            ),
            (
                "buildings",
                "geo_buildings",
                "source = 'overture' AND region = $1",
            ),
        ):
            rows: list[dict[str, SqlParameterValue]] = await execute_raw(
                f"SELECT count(*)::int AS c FROM {table} WHERE {where}",
                [region],
                using="geo",
            )
            await GeoStats.set_rows(
                generation=0,
                source=_SOURCE,
                region=region,
                entity=entity,
                rows=int(str(rows[0]["c"])) if rows else 0,
            )


__all__ = [
    "OvertureImportService",
    "OvertureSyncResult",
    "_wkb_to_geojson",
]

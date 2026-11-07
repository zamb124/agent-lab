"""Векторная базовая карта: PMTiles/шрифты/спрайты/style.json.

Отдаёт файлы из ``GeoSettings.tiles_dir`` — их наполняет ``geo_tiles_sync``
или ``scripts/geo/fetch_basemap.py``. ``basemap.pmtiles`` читается
клиентом (pmtiles.js) через HTTP Range GET — поэтому отдача потоковая с
206/Content-Range/Accept-Ranges. Эндпоинты анонимные (см. route_config):
ассеты статичны и публичны как ``/static``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from apps.geo.di import Di
from core.errors.boundary import PlatformNotFoundError
from core.files.http_range import RangeNotSatisfiableError, normalize_s3_byte_range

router = APIRouter(tags=["geo-tiles"])

_CHUNK = 64 * 1024
# fontstack — одно или несколько имён шрифтов через запятую: MapLibre
# склеивает массив text-font запятыми («Open Sans Regular,Arial
# Unicode MS Regular»); пустые сегменты и прочие символы — 404.
_FONTSTACK_RE = re.compile(r"^[A-Za-z0-9 ._'-]+(,[A-Za-z0-9 ._'-]+)*$")
_RANGE_RE = re.compile(r"^\d+-\d+\.pbf$")
_SPRITE_RE = re.compile(r"^v\d/[a-z0-9@_]+\.(json|png)$")

_MEDIA = {
    ".pmtiles": "application/vnd.pmtiles",
    ".pbf": "application/x-protobuf",
    ".json": "application/json",
    ".png": "image/png",
}


def _safe_path(root: Path, *parts: str) -> Path:
    """Резолвит дочерний путь внутри ``root``; выход за корень → 404."""
    target = (root / Path(*parts)).resolve()
    if root != target.parent and root not in target.parents:
        raise PlatformNotFoundError("Tile asset not found", error_code="tile_not_found")
    if not target.is_file():
        raise PlatformNotFoundError("Tile asset not found", error_code="tile_not_found")
    return target


def _etag(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha256(f"{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()
    return f'"{digest[:32]}"'


def _read_range(path: Path, start: int, end: int) -> AsyncIterator[bytes]:
    """Асинхронный итератор чанков ``[start, end]`` файла через to_thread."""

    async def _iterate() -> AsyncIterator[bytes]:
        fh = await asyncio.to_thread(path.open, "rb")
        try:
            _ = await asyncio.to_thread(fh.seek, start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = await asyncio.to_thread(fh.read, min(_CHUNK, remaining))
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)
        finally:
            await asyncio.to_thread(fh.close)

    return _iterate()


async def _serve_file(
    path: Path,
    request: Request,
    *,
    media_type: str,
    cache_seconds: int,
) -> Response:
    """Отдача локального файла с Range/ETag/Cache-Control."""
    total = path.stat().st_size
    etag = _etag(path)
    base_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": f"public, max-age={cache_seconds}",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=base_headers)
    if request.method == "HEAD":
        return Response(headers={**base_headers, "Content-Length": str(total)})

    try:
        span = normalize_s3_byte_range(request.headers.get("range"), total)
    except RangeNotSatisfiableError as exc:
        return Response(
            status_code=416,
            headers={**base_headers, "Content-Range": f"bytes */{exc.total_size}"},
        )

    if span is None:
        stream = _read_range(path, 0, total - 1)
        return StreamingResponse(
            stream,
            media_type=media_type,
            headers={**base_headers, "Content-Length": str(total)},
        )
    start, end = span
    return StreamingResponse(
        _read_range(path, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            **base_headers,
            "Content-Length": str(end - start + 1),
            "Content-Range": f"bytes {start}-{end}/{total}",
        },
    )


def _tiles_root(di: Di) -> Path:
    return Path(di.settings.tiles_dir).resolve()


@router.api_route("/tiles/basemap.pmtiles", methods=["GET", "HEAD"])
async def tiles_basemap(request: Request, di: Di) -> Response:
    """PMTiles-архив региона покрытия — Range GET читает pmtiles.js."""
    path = _safe_path(_tiles_root(di), "basemap.pmtiles")
    return await _serve_file(
        path,
        request,
        media_type=_MEDIA[".pmtiles"],
        cache_seconds=di.settings.tiles_cache_seconds,
    )


@router.api_route("/tiles/fonts/{fontstack}/{pbf_range}", methods=["GET", "HEAD"])
async def tiles_fonts(request: Request, di: Di, fontstack: str, pbf_range: str) -> Response:
    """Glyph-стеки MapLibre: ``{fontstack}/{range}.pbf``."""
    if not _FONTSTACK_RE.match(fontstack) or not _RANGE_RE.match(pbf_range):
        raise PlatformNotFoundError("Font asset not found", error_code="tile_not_found")
    path = _safe_path(_tiles_root(di), "fonts", fontstack, pbf_range)
    return await _serve_file(
        path,
        request,
        media_type=_MEDIA[".pbf"],
        cache_seconds=di.settings.tiles_cache_seconds,
    )


@router.api_route("/tiles/sprites/{filename:path}", methods=["GET", "HEAD"])
async def tiles_sprites(request: Request, di: Di, filename: str) -> Response:
    """Спрайты MapLibre: ``v<ver>/{flavor}.{json,png}`` (включая ``@2x``)."""
    if not _SPRITE_RE.match(filename):
        raise PlatformNotFoundError("Sprite asset not found", error_code="tile_not_found")
    path = _safe_path(_tiles_root(di), "sprites", filename)
    media = _MEDIA.get(path.suffix, "application/octet-stream")
    return await _serve_file(
        path,
        request,
        media_type=media,
        cache_seconds=di.settings.tiles_cache_seconds,
    )


_STYLE_DIR = Path(__file__).resolve().parent.parent / "tiles"
_STYLE_PATHS = {
    "light": _STYLE_DIR / "style-light.json",
    "dark": _STYLE_DIR / "style-dark.json",
}


@router.get("/tiles/style.json")
async def tiles_style(request: Request, scheme: str = "light") -> JSONResponse:
    """MapLibre style с нашими URL: pmtiles-источник, glyphs, sprites.

    ``scheme`` — ``light`` (по умолчанию) или ``dark``; любое другое
    значение — 404, allowlist как у остальных tile-маршрутов.
    """
    path = _STYLE_PATHS.get(scheme)
    if path is None:
        raise PlatformNotFoundError("Unknown style scheme", error_code="tile_not_found")
    base = f"{request.url.scheme}://{request.url.netloc}{request.scope.get('root_path', '')}"
    tiles = f"{base}/geo/api/v1/tiles"
    raw = path.read_text(encoding="utf-8")
    return JSONResponse(
        json.loads(raw.replace("__TILES_URL__", tiles)),
        headers={
            "Cache-Control": "public, max-age=300",
            "ETag": _etag(path),
        },
    )

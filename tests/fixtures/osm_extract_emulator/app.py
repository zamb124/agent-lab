"""Эмулятор HTTP-зеркала OSM-экстрактов для тестового стека.

Внешний источник ``GEO__OSM_EXTRACT_URLS`` заменяется локальным сервером
того же протокола (testing.mdc § Канон): HEAD отдаёт ``Last-Modified``, GET —
байты ``tests/geo/fixtures/micro.osm.pbf``. Так в тестах проходит реальный
wire-путь ``OsmImportService._download_if_newer`` (HEAD → If-Modified-Since →
стриминг в tmp → pyosmium-парс), а не ``file://``.
"""

import io
import tarfile
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response

_FIXTURE = (
    Path(__file__).resolve().parents[2] / "geo" / "fixtures" / "micro.osm.pbf"
)
_LAST_MODIFIED = format_datetime(
    datetime.fromtimestamp(_FIXTURE.stat().st_mtime, UTC), usegmt=True
)

app = FastAPI(title="platform-osm-extract-emulator")


def _body() -> bytes:
    return _FIXTURE.read_bytes()


@app.head("/extracts/micro.osm.pbf")
async def head_extract() -> Response:
    return Response(
        status_code=200,
        headers={
            "Last-Modified": _LAST_MODIFIED,
            "Content-Length": str(_FIXTURE.stat().st_size),
            "Content-Type": "application/octet-stream",
        },
    )


@app.get("/extracts/micro.osm.pbf")
async def get_extract() -> Response:
    return Response(
        content=_body(),
        media_type="application/octet-stream",
        headers={"Last-Modified": _LAST_MODIFIED},
    )


@app.head("/extracts/no-last-modified.osm.pbf")
async def head_extract_no_lm() -> Response:
    """Зеркало без Last-Modified: источник считается всегда свежим."""
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(_FIXTURE.stat().st_size),
            "Content-Type": "application/octet-stream",
        },
    )


@app.get("/extracts/no-last-modified.osm.pbf")
async def get_extract_no_lm() -> Response:
    return Response(content=_body(), media_type="application/octet-stream")


def _assets_tarball() -> bytes:
    """Синтетический basemaps-assets tar.gz: fonts/ + sprites/ внутри
    корневой директории архива (как у protomaps/basemaps-assets)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def _add(name: str, payload: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        _add("basemaps-assets/fonts/Noto Sans Regular/0-255.pbf", b"glyphs-synced")
        _add("basemaps-assets/sprites/v4/light.json", b'{"synced":true}')
        _add("basemaps-assets/sprites/v4/light.png", b"\x89PNG-synced")
    return buf.getvalue()


@app.get("/tiles-assets/basemaps-assets.tar.gz")
async def get_tiles_assets() -> Response:
    """Зеркало ``tiles_assets_url`` для ``GeoTilesService._sync_assets``."""
    return Response(
        content=_assets_tarball(),
        media_type="application/gzip",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

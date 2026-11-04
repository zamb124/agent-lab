"""Эмулятор HTTP-зеркала OSM-экстрактов для тестового стека.

Внешний источник ``GEO__OSM_EXTRACT_URLS`` заменяется локальным сервером
того же протокола (testing.mdc § Канон): HEAD отдаёт ``Last-Modified``, GET —
байты ``tests/geo/fixtures/micro.osm.pbf``. Так в тестах проходит реальный
wire-путь ``OsmImportService._download_if_newer`` (HEAD → If-Modified-Since →
стриминг в tmp → pyosmium-парс), а не ``file://``.
"""

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

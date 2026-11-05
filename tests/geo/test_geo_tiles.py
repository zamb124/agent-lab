"""Векторные тайлы geo: Range-отдача PMTiles, fonts/sprites, style.json.

Тесты бьют в живой geo granian тестового стека (``SERVER__GEO_SERVICE_URL``
→ ``http://127.0.0.1:9028``): ``TILES_DIR`` процесса — коммиченные фикстуры
``tests/geo/fixtures/tiles`` (см. ``scripts/testing/stack.py``).
"""

from pathlib import Path

import pytest
import pytest_asyncio
from httpx2 import AsyncClient

from core.types import JsonValue

pytestmark = pytest.mark.xdist_group("geo")

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tiles"
_PMTILES_BYTES = _FIXTURE.joinpath("basemap.pmtiles").read_bytes()
_GEO_BASE = "http://127.0.0.1:9028"
_BASE = "/geo/api/v1/tiles"


@pytest_asyncio.fixture
async def geo_client():
    async with AsyncClient(base_url=_GEO_BASE, timeout=15.0) as ac:
        yield ac


async def test_basemap_full_get(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(f"{_BASE}/basemap.pmtiles")
    assert resp.status_code == 200
    assert resp.content == _PMTILES_BYTES
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-length"] == str(len(_PMTILES_BYTES))
    assert "etag" in resp.headers


async def test_basemap_range_get(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(
        f"{_BASE}/basemap.pmtiles", headers={"range": "bytes=10-99"}
    )
    assert resp.status_code == 206
    assert resp.content == _PMTILES_BYTES[10:100]
    assert resp.headers["content-range"] == f"bytes 10-99/{len(_PMTILES_BYTES)}"
    assert resp.headers["content-length"] == "90"


async def test_basemap_range_open_end(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(
        f"{_BASE}/basemap.pmtiles", headers={"range": "bytes=1000-"}
    )
    assert resp.status_code == 206
    assert resp.content == _PMTILES_BYTES[1000:]


async def test_basemap_range_suffix(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(
        f"{_BASE}/basemap.pmtiles", headers={"range": "bytes=-16"}
    )
    assert resp.status_code == 206
    assert resp.content == _PMTILES_BYTES[-16:]


async def test_basemap_range_unsatisfiable(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(
        f"{_BASE}/basemap.pmtiles",
        headers={"range": f"bytes={len(_PMTILES_BYTES) + 10}-"},
    )
    assert resp.status_code == 416
    assert resp.headers["content-range"] == f"bytes */{len(_PMTILES_BYTES)}"


async def test_basemap_head(geo_client: AsyncClient) -> None:
    resp = await geo_client.head(f"{_BASE}/basemap.pmtiles")
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-length"] == str(len(_PMTILES_BYTES))
    assert not resp.content


async def test_basemap_etag_304(geo_client: AsyncClient) -> None:
    first = await geo_client.get(f"{_BASE}/basemap.pmtiles")
    etag = first.headers["etag"]
    second = await geo_client.get(
        f"{_BASE}/basemap.pmtiles", headers={"if-none-match": etag}
    )
    assert second.status_code == 304


async def test_basemap_missing_404(geo_client: AsyncClient) -> None:
    # Валидное имя, отсутствующего диапазона глифов → 404 (не 500/пусто).
    resp = await geo_client.get(f"{_BASE}/fonts/Noto Sans Regular/65280-65535.pbf")
    assert resp.status_code == 404


async def test_fonts_get(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(f"{_BASE}/fonts/Noto Sans Regular/0-255.pbf")
    assert resp.status_code == 200
    assert resp.content == b"glyphs-0-255-fixture"


async def test_fonts_bad_name_404(geo_client: AsyncClient) -> None:
    for bad in ("not-a-range.pbf", "..%2Fbasemap.pmtiles", "x-y.pbf"):
        resp = await geo_client.get(f"{_BASE}/fonts/Noto Sans Regular/{bad}")
        assert resp.status_code == 404, bad


async def test_sprites_get(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(f"{_BASE}/sprites/v4/light.json")
    assert resp.status_code == 200
    assert resp.content == b'{"poi":{}}'
    png = await geo_client.get(f"{_BASE}/sprites/v4/light.png")
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"


async def test_sprites_bad_name_404(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(f"{_BASE}/sprites/evil.exe")
    assert resp.status_code == 404


async def test_style_json_urls(geo_client: AsyncClient) -> None:
    resp = await geo_client.get(f"{_BASE}/style.json")
    assert resp.status_code == 200
    style: dict[str, JsonValue] = resp.json()
    assert style["version"] == 8
    glyphs = style["glyphs"]
    assert isinstance(glyphs, str)
    assert glyphs.endswith("/geo/api/v1/tiles/fonts/{fontstack}/{range}.pbf")
    sprite = style["sprite"]
    assert isinstance(sprite, str)
    assert sprite.endswith("/geo/api/v1/tiles/sprites/v4/light")
    sources = style["sources"]
    assert isinstance(sources, dict)
    basemap = sources["basemap"]
    assert isinstance(basemap, dict)
    url = basemap["url"]
    assert isinstance(url, str)
    assert url.startswith("pmtiles://") and url.endswith(
        "/geo/api/v1/tiles/basemap.pmtiles"
    )
    attribution = basemap["attribution"]
    assert isinstance(attribution, str)
    assert "OpenStreetMap" in attribution
    layers = style["layers"]
    assert isinstance(layers, list)
    assert len(layers) > 50

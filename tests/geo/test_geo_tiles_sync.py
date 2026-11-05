"""GeoTilesService.sync: provision basemap.pmtiles + fonts/sprites.

Реальный wire-путь без моков: ``pmtiles extract`` — исполняемый скрипт в
tmp (тот же subprocess-контракт: ``extract SRC DST --bbox=...``), ассеты —
реальный HTTP GET из ``osm_extract_emulator`` (:18099) с настоящим tar.gz.
"""

import stat
from pathlib import Path

import pytest

from apps.geo.config import GeoSettings
from apps.geo.services.geo_tiles_service import GeoTilesService
from core.errors.boundary import PlatformUnavailableError

pytestmark = pytest.mark.xdist_group("geo")

_EMULATOR = "http://127.0.0.1:18099"
_ASSETS_URL = f"{_EMULATOR}/tiles-assets/basemaps-assets.tar.gz"


def _fake_pmtiles(tmp_path: Path, body: str) -> str:
    """Исполняемый фейк ``pmtiles`` с контрактом ``extract SRC DST --bbox``."""
    script = tmp_path / "pmtiles"
    _ = script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return str(script)


def _svc(tmp_path: Path, **overrides: object) -> GeoTilesService:
    kwargs: dict[str, object] = {
        "tiles_dir": str(tmp_path / "tiles"),
        "tiles_assets_url": _ASSETS_URL,
    }
    kwargs.update(overrides)
    return GeoTilesService(GeoSettings.model_validate(kwargs))


async def test_pmtiles_promotes_staging_to_target(tmp_path: Path) -> None:
    bin_path = _fake_pmtiles(
        tmp_path, '#!/bin/sh\nprintf "archive-bytes" > "$3"\n'
    )
    root = tmp_path / "tiles"
    result = await _svc(tmp_path, tiles_pmtiles_bin=bin_path).sync()
    assert (root / "basemap.pmtiles").read_bytes() == b"archive-bytes"
    assert not (root / "basemap.pmtiles.next").exists()
    assert result["basemap_bytes"] == len(b"archive-bytes")


async def test_pmtiles_failure_cleans_staging(tmp_path: Path) -> None:
    bin_path = _fake_pmtiles(
        tmp_path, '#!/bin/sh\nprintf "partial" > "$3"\nexit 1\n'
    )
    root = tmp_path / "tiles"
    with pytest.raises(PlatformUnavailableError):
        _ = await _svc(tmp_path, tiles_pmtiles_bin=bin_path).sync()
    assert not (root / "basemap.pmtiles").exists()
    assert not (root / "basemap.pmtiles.next").exists()


async def test_pmtiles_keeps_existing_archive_on_failure(tmp_path: Path) -> None:
    """Провал нового extract не трогает валидный старый архив."""
    bin_path = _fake_pmtiles(tmp_path, "#!/bin/sh\nexit 1\n")
    root = tmp_path / "tiles"
    root.mkdir(parents=True)
    _ = (root / "basemap.pmtiles").write_bytes(b"old-good")
    with pytest.raises(PlatformUnavailableError):
        _ = await _svc(tmp_path, tiles_pmtiles_bin=bin_path).sync()
    assert (root / "basemap.pmtiles").read_bytes() == b"old-good"


async def test_pmtiles_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(PlatformUnavailableError):
        _ = await _svc(tmp_path, tiles_pmtiles_bin="/nonexistent/pmtiles").sync()


async def test_assets_atomic_swap_replaces_stub_dirs(tmp_path: Path) -> None:
    """Пустые/стабовые fonts+sprites перезаписываются реальными файлами."""
    bin_path = _fake_pmtiles(
        tmp_path, '#!/bin/sh\nprintf "archive" > "$3"\n'
    )
    root = tmp_path / "tiles"
    (root / "fonts" / "Stub").mkdir(parents=True)
    _ = (root / "fonts" / "Stub" / "junk.pbf").write_bytes(b"junk")
    (root / "sprites").mkdir(parents=True)
    _ = (root / "sprites" / "junk.json").write_text("{}")
    result = await _svc(tmp_path, tiles_pmtiles_bin=bin_path).sync()
    assert result["assets"] == "synced"
    assert (root / "fonts" / "Noto Sans Regular" / "0-255.pbf").read_bytes() == (
        b"glyphs-synced"
    )
    assert (root / "sprites" / "v4" / "light.json").read_text() == '{"synced":true}'
    assert not (root / "fonts" / "Stub").exists()
    assert not (root / "sprites" / "junk.json").exists()
    for name in ("fonts.staged", "fonts.old", "sprites.staged", "sprites.old"):
        assert not (root / name).exists(), name


async def test_assets_http_error_raises_unavailable(tmp_path: Path) -> None:
    bin_path = _fake_pmtiles(
        tmp_path, '#!/bin/sh\nprintf "archive" > "$3"\n'
    )
    with pytest.raises(PlatformUnavailableError):
        _ = await _svc(
            tmp_path,
            tiles_pmtiles_bin=bin_path,
            tiles_assets_url=f"{_EMULATOR}/extracts/404",
        ).sync()
    # Архив на месте (extract прошёл), ассеты не появились.
    assert (tmp_path / "tiles" / "basemap.pmtiles").is_file()
    assert not (tmp_path / "tiles" / "sprites").exists()


async def test_sync_full(tmp_path: Path) -> None:
    bin_path = _fake_pmtiles(
        tmp_path, '#!/bin/sh\nprintf "archive" > "$3"\n'
    )
    root = tmp_path / "tiles"
    result = await _svc(tmp_path, tiles_pmtiles_bin=bin_path).sync()
    assert result["basemap_bytes"] == len(b"archive")
    assert result["assets"] == "synced"
    assert (root / "basemap.pmtiles").is_file()
    assert (root / "sprites" / "v4" / "light.png").is_file()

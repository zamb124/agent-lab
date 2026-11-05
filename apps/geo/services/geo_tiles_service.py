"""Векторная базовая карта: provision PMTiles-extract и glyph/sprite-ассетов."""

from __future__ import annotations

import asyncio
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

from apps.geo.config import GeoSettings
from core.errors.boundary import PlatformUnavailableError
from core.http import get_httpx_client
from core.types import SqlParameterValue


class GeoTilesService:
    """Качает региональный PMTiles и ассеты стиля в ``tiles_dir``."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def sync(self) -> dict[str, SqlParameterValue]:
        """pmtiles extract по coverage_bbox → атомарный своп basemap.pmtiles
        + дозаливка fonts/sprites при отсутствии."""
        root = Path(self._settings.tiles_dir)
        root.mkdir(parents=True, exist_ok=True)
        result = await self._sync_pmtiles(root)
        assets = await self._sync_assets(root)
        return {**result, **assets}

    async def _sync_pmtiles(self, root: Path) -> dict[str, SqlParameterValue]:
        lat_min, lng_min, lat_max, lng_max = self._settings.coverage_bbox
        bbox = f"{lng_min},{lat_min},{lng_max},{lat_max}"
        target = root / "basemap.pmtiles"
        staging = root / "basemap.pmtiles.next"
        root.mkdir(parents=True, exist_ok=True)
        staging.unlink(missing_ok=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._settings.tiles_pmtiles_bin,
                "extract",
                self._settings.tiles_pmtiles_source,
                str(staging),
                f"--bbox={bbox}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise PlatformUnavailableError(
                f"pmtiles CLI not found: {self._settings.tiles_pmtiles_bin} " +
                "(go install github.com/protomaps/go-pmtiles/pmtiles@latest)",
                error_code="tiles_extract_failed",
            ) from exc
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not staging.is_file():
            staging.unlink(missing_ok=True)
            raise PlatformUnavailableError(
                f"pmtiles extract failed (rc={proc.returncode}): " + stderr.decode('utf-8', 'replace')[-500:],
                error_code="tiles_extract_failed",
            )
        os.replace(staging, target)
        return {
            "basemap_bytes": target.stat().st_size,
            "basemap_bbox": bbox,
        }

    async def _sync_assets(self, root: Path) -> dict[str, SqlParameterValue]:
        """basemaps-assets tar.gz → fonts/ + sprites/, атомарный своп."""
        url = self._settings.tiles_assets_url
        async with get_httpx_client(timeout=600) as client:
            resp = await client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            raise PlatformUnavailableError(
                f"tiles assets download failed: HTTP {resp.status_code}",
                error_code="tiles_assets_failed",
            )
        with tempfile.TemporaryDirectory(prefix="geo-tiles-assets-") as tmp:
            archive = Path(tmp) / "assets.tar.gz"
            _ = archive.write_bytes(resp.content)
            extracted = Path(tmp) / "src"
            extracted.mkdir()
            with tarfile.open(archive) as tar:
                tar.extractall(extracted, filter="data")
            src_root = next(extracted.iterdir())
            for name in ("fonts", "sprites"):
                src = src_root / name
                dst = root / name
                staged = root / f"{name}.staged"
                if not src.is_dir():
                    raise PlatformUnavailableError(
                        f"tiles assets archive lacks '{name}/'",
                        error_code="tiles_assets_failed",
                    )
                if staged.is_dir():
                    shutil.rmtree(staged)
                _ = shutil.move(str(src), str(staged))
                old = root / f"{name}.old"
                if old.is_dir():
                    shutil.rmtree(old)
                if dst.is_dir():
                    _ = dst.rename(old)
                _ = staged.rename(dst)
                if old.is_dir():
                    shutil.rmtree(old)
        return {"assets": "synced"}

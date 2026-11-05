#!/usr/bin/env python3
"""Dev-provision векторной карты: ``python -m scripts.geo.fetch_basemap``.

Вызывает ``GeoTilesService.sync`` напрямую (без очереди): кладёт
``basemap.pmtiles`` + ``fonts/`` + ``sprites/`` в ``GeoSettings.tiles_dir``.
"""

import asyncio

from apps.geo.config import GeoSettings
from apps.geo.services.geo_tiles_service import GeoTilesService


async def main() -> None:
    result = await GeoTilesService(GeoSettings()).sync()
    for key, value in result.items():
        print(f"{key}: {value}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

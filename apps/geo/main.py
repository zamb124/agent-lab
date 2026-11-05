"""
Geo Service — гео-движок платформы.

Порт: 8028
БД: platform_geo (PostGIS + pgRouting: адреса, дорожный граф)

SPA — отладочный интерфейс канонических слоёв: карта (`<geo-map>` +
`<geo-layer-panel>`), реестр покрытия, маршрутная лаборатория.
Продуктовые потребители ходят через `GeoClient` или op_* шины.
"""

from pathlib import Path

from apps.geo.api import get_api_router
from apps.geo.config import GeoSettings
from apps.geo.di import GeoDi
from apps.geo.realtime.command_router import GEO_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings

app = create_service_app(
    "geo",
    GeoSettings,
    GeoDi,
    database="geo_url",
    operations=GEO_OPERATIONS,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[get_api_router()],
    title="Geo Service",
    description="Адресный справочник, зоны и роутинг платформы (PostGIS/pgRouting)",
    api_version="v1",
)

mount_service_spa(app, public_segment="geo", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("geo", "apps.geo.main:app", get_settings())

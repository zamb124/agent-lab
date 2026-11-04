"""
Geo Service — гео-движок платформы.

Порт: 8028
БД: platform_geo (PostGIS + pgRouting: адреса, дорожный граф)

SPA у сервиса нет — UI-компоненты карт живут в core UI kit
(``core/frontend/static/lib/components/map/``), потребители ходят через
``GeoClient`` или op_* шины.
"""

from apps.geo.api import get_api_router
from apps.geo.config import GeoSettings
from apps.geo.di import GeoDi
from apps.geo.realtime.command_router import GEO_OPERATIONS
from core.app import create_service_app
from core.config import get_settings

app = create_service_app(
    "geo",
    GeoSettings,
    GeoDi,
    database="geo_url",
    operations=GEO_OPERATIONS,
    routers=[get_api_router()],
    title="Geo Service",
    description="Адресный справочник, зоны и роутинг платформы (PostGIS/pgRouting)",
    api_version="v1",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("geo", "apps.geo.main:app", get_settings())

"""DI процесса geo: адресный справочник, роутинг, импорт OSM."""

from typing import Annotated

from apps.geo.config import GeoSettings
from apps.geo.services.geo_address_service import GeoAddressService
from apps.geo.services.geo_routing_service import GeoRoutingService
from apps.geo.services.osm_import_service import OsmImportService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class GeoDi(PlatformDi):
    settings: GeoSettings
    geo_address_service: GeoAddressService
    geo_routing_service: GeoRoutingService
    osm_import_service: OsmImportService


Di = Annotated[GeoDi, http_di(GeoDi), task_di(GeoDi)]

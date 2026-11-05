"""DI процесса geo: адресный справочник, роутинг, импорт, реестр покрытия."""

from typing import Annotated

from apps.geo.config import GeoSettings
from apps.geo.services.geo_address_service import GeoAddressService
from apps.geo.services.geo_coverage_service import GeoCoverageService
from apps.geo.services.geo_layer_service import GeoLayerService
from apps.geo.services.geo_routing_service import GeoRoutingService
from apps.geo.services.geo_tiles_service import GeoTilesService
from apps.geo.services.osm_import_service import OsmImportService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class GeoDi(PlatformDi):
    settings: GeoSettings
    geo_address_service: GeoAddressService
    geo_coverage_service: GeoCoverageService
    geo_layer_service: GeoLayerService
    geo_routing_service: GeoRoutingService
    geo_tiles_service: GeoTilesService
    osm_import_service: OsmImportService


Di = Annotated[GeoDi, http_di(GeoDi), task_di(GeoDi)]

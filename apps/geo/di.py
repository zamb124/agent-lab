"""DI процесса geo: адресный справочник, роутинг, импорт, реестр покрытия."""

from typing import Annotated

from apps.geo.config import GeoSettings
from apps.geo.services.datamos_import_service import DataMosImportService
from apps.geo.services.gar_import_service import GarImportService
from apps.geo.services.geo_address_service import GeoAddressService
from apps.geo.services.geo_admin_service import GeoAdminService
from apps.geo.services.geo_coverage_service import GeoCoverageService
from apps.geo.services.geo_enrich_service import GeoEnrichService
from apps.geo.services.geo_layer_service import GeoLayerService
from apps.geo.services.geo_routing_service import GeoRoutingService
from apps.geo.services.geo_tiles_service import GeoTilesService
from apps.geo.services.nspd_crawl_service import NspdCrawlService
from apps.geo.services.osm_diff_service import OsmDiffService
from apps.geo.services.osm_import_service import OsmImportService
from apps.geo.services.overture_import_service import OvertureImportService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class GeoDi(PlatformDi):
    settings: GeoSettings
    geo_address_service: GeoAddressService
    geo_admin_service: GeoAdminService
    geo_coverage_service: GeoCoverageService
    geo_enrich_service: GeoEnrichService
    geo_layer_service: GeoLayerService
    geo_routing_service: GeoRoutingService
    geo_tiles_service: GeoTilesService
    datamos_import_service: DataMosImportService
    gar_import_service: GarImportService
    nspd_crawl_service: NspdCrawlService
    osm_diff_service: OsmDiffService
    osm_import_service: OsmImportService
    overture_import_service: OvertureImportService


Di = Annotated[GeoDi, http_di(GeoDi), task_di(GeoDi)]

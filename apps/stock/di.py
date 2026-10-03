"""DI процесса stock: складской леджер, оценка, рефлексы."""

from typing import Annotated

from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.catalog_service import CatalogService
from apps.stock.services.company_init_service import StockCompanyInitService
from apps.stock.services.maintenance_service import MaintenanceService
from apps.stock.services.move_engine import StockMoveEngine
from apps.stock.services.placement_service import PlacementService
from apps.stock.services.pulse_service import PulseService
from apps.stock.services.rule_service import RuleService
from apps.stock.services.scan_service import ScanService
from apps.stock.services.stock_access_service import StockAccessService
from apps.stock.services.task_service import TaskService
from apps.stock.services.topology_service import TopologyService
from apps.stock.services.valuation_service import ValuationService
from apps.stock.services.warehouse_service import WarehouseService
from apps.stock.services.wave_service import WaveService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class StockDi(PlatformDi):
    barcode_service: BarcodeService
    scan_service: ScanService
    move_engine: StockMoveEngine
    warehouse_service: WarehouseService
    catalog_service: CatalogService
    placement_service: PlacementService
    rule_service: RuleService
    valuation_service: ValuationService
    topology_service: TopologyService
    pulse_service: PulseService
    company_init_service: StockCompanyInitService
    stock_access_service: StockAccessService
    task_service: TaskService
    wave_service: WaveService
    maintenance_service: MaintenanceService


Di = Annotated[StockDi, http_di(StockDi), task_di(StockDi)]

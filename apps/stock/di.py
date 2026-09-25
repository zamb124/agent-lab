"""DI процесса stock: складской леджер, оценка, рефлексы."""

from typing import Annotated

from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.company_init_service import StockCompanyInitService
from apps.stock.services.move_engine import StockMoveEngine
from apps.stock.services.pulse_service import PulseService
from apps.stock.services.putaway_service import PutawayService
from apps.stock.services.stock_access_service import StockAccessService
from apps.stock.services.valuation_service import ValuationService
from apps.stock.services.warehouse_service import WarehouseService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class StockDi(PlatformDi):
    barcode_service: BarcodeService
    putaway_service: PutawayService
    move_engine: StockMoveEngine
    warehouse_service: WarehouseService
    valuation_service: ValuationService
    pulse_service: PulseService
    company_init_service: StockCompanyInitService
    stock_access_service: StockAccessService


Di = Annotated[StockDi, http_di(StockDi), task_di(StockDi)]

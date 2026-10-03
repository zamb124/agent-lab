"""DI процесса stock_worker: тики reconcile/claims/reorder/cycle_count."""

from typing import Annotated

from apps.stock.services.maintenance_service import MaintenanceService
from apps.stock.services.move_engine import StockMoveEngine
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class StockWorkerDi(PlatformDi):
    move_engine: StockMoveEngine
    maintenance_service: MaintenanceService


Di = Annotated[StockWorkerDi, http_di(StockWorkerDi), task_di(StockWorkerDi)]

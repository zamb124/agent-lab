"""Stock Worker (очередь ``stock``).

Фоновые тики склада: сверка леджера, возврат брошенных захватов
заданий, min/max пополнение, плановый пересчёт ячеек. Все правки
остатков — только через полосы складов (``stock_command_lane``),
этот процесс не является транспортом команд.

Запуск: taskiq worker apps.stock.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.stock.config import StockSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = StockSettings.model_validate(
    load_merged_config(service_name="stock_worker", silent=True)
)
setup_worker_logging_early("stock_worker", logging_config=_settings.logging)
set_settings(_settings)
set_files_route_segment(resolve_files_route_segment("stock_worker"))

from apps.stock.di import StockDi
from apps.worker_manifest import wire_worker
from core.tasks.worker_bootstrap import build_worker

broker = wire_worker("stock")
worker_app = build_worker(
    broker,
    service_name="stock_worker",
    queue="stock",
    settings=_settings,
    di_class=StockDi,
    database="stock_url",
)

__all__ = ["worker_app"]

"""Shop Worker (очередь ``shop``).

Фоновая работа витрин: пересборка Redis-снапшотов, Telegram-уведомления
о заказах, провиженинг кастомных доменов, ребилд агрегатора. Этот процесс
не является транспортом команд — только тяжёлая и вторичная работа.

Запуск: taskiq worker apps.shop.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.shop.config import ShopSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = ShopSettings.model_validate(
    load_merged_config(service_name="shop_worker", silent=True)
)
setup_worker_logging_early("shop_worker", logging_config=_settings.logging)
set_settings(_settings)
set_files_route_segment(resolve_files_route_segment("shop_worker"))

from apps.shop.di import ShopDi
from apps.worker_manifest import wire_worker
from core.tasks.worker_bootstrap import build_worker

broker = wire_worker("shop")
worker_app = build_worker(
    broker,
    service_name="shop_worker",
    queue="shop",
    settings=_settings,
    di_class=ShopDi,
    database="shop_url",
)

__all__ = ["worker_app"]

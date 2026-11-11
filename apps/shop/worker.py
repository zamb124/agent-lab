"""Shop Worker (очередь ``shop``).

Фоновая работа витрин: пересборка Redis-снапшотов, Telegram-уведомления
о заказах, провиженинг кастомных доменов, ребилд агрегатора. Consumer
group ``shop`` шины ``platform:events`` инвалидирует снапшоты и
проекцию ``shop_market_items`` по ``catalog/product/*``. Этот процесс
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

import os
import socket
from collections.abc import AsyncIterator

from apps.shop.di import ShopDi
from apps.shop.services.aggregate_service import AggregateService
from apps.worker_manifest import wire_worker
from core.di import recipe
from core.events import PlatformEvent, PlatformEventGroupConsumer
from core.tasks.worker_bootstrap import build_worker
from core.utils.background import finish_background_task, run_with_log_context

broker = wire_worker("shop")


async def run_shop_platform_events(
    aggregate_service: AggregateService,
) -> AsyncIterator[None]:
    """Durable-подписка на ``catalog/*``: инвалидация проекций витрин."""

    async def on_event(event: PlatformEvent) -> None:
        if event.type.startswith("catalog/"):
            await aggregate_service.handle_catalog_event(event)

    consumer = PlatformEventGroupConsumer(
        group="shop",
        consumer_name=f"{socket.gethostname()}-{os.getpid()}",
        on_event=on_event,
    )
    consumer_task = run_with_log_context(
        consumer.run(),
        name="platform_events.shop_consumer",
        background_kind="startup",
    )
    yield
    await finish_background_task(consumer_task)


worker_app = build_worker(
    broker,
    service_name="shop_worker",
    queue="shop",
    settings=_settings,
    di_class=ShopDi,
    database="shop_url",
    lifecycle=(recipe(run_shop_platform_events),),
)

__all__ = ["worker_app"]

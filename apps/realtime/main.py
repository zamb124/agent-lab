"""
Realtime bus — единственный HTTP-peer Centrifugo.

Порт: 8025
БД: platform_realtime
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI

from apps.realtime.api import get_api_router
from apps.realtime.config import RealtimeSettings
from apps.realtime.container import RealtimeContainer, get_realtime_container
from core.app import create_service_app
from core.config import get_settings
from core.logging import get_logger
from core.realtime.submit import bind_local_event_ingest, unbind_local_event_ingest
from core.utils.background import run_with_log_context

logger = get_logger(__name__)

_sweeper_task: asyncio.Task[None] | None = None


async def _sweep_loop(container: RealtimeContainer) -> None:
    interval = get_settings().realtime.sweeper_interval_seconds
    while True:
        await asyncio.sleep(interval)
        swept = await container.bus_service.sweep_expired_commands()
        if swept:
            logger.info("realtime.sweeper.expired", count=swept)


async def on_startup(app: FastAPI, container: RealtimeContainer, settings: RealtimeSettings) -> None:
    _ = app, settings
    bind_local_event_ingest(container.bus_service.ingest)
    global _sweeper_task
    _sweeper_task = run_with_log_context(
        _sweep_loop(container),
        name="realtime.sweeper",
        background_kind="polling",
    )
    logger.info("Realtime bus: запущен")


async def on_shutdown(app: FastAPI, container: RealtimeContainer) -> None:
    _ = app, container
    global _sweeper_task
    if _sweeper_task is not None:
        _ = _sweeper_task.cancel()
        _sweeper_task = None
    unbind_local_event_ingest()
    logger.info("Realtime bus: остановлен")


app = create_service_app(
    service_name="realtime",
    settings_class=RealtimeSettings,
    get_container=get_realtime_container,
    routers=[get_api_router()],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    title="Realtime Bus",
    description="Durable-лог PlatformEvent и единственный HTTP-peer Centrifugo",
    api_version="v1",
    include_crud_routers=False,
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("realtime", "apps.realtime.main:app", get_settings())

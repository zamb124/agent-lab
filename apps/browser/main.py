"""
Сервис browser: Browser Runtime v1, health, минимальный control-plane HTTP.
"""

import asyncio
from contextlib import suppress

from fastapi import FastAPI

from apps.browser.api.control import router as browser_control_router
from apps.browser.api.crawl_fetch import router as browser_crawl_fetch_router
from apps.browser.api.health import router as browser_health_router
from apps.browser.api.mcp import router as browser_mcp_router
from apps.browser.config import BrowserSettings, get_browser_settings
from apps.browser.container import BrowserContainer, get_browser_container
from core.app import create_service_app
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


async def _reaper_loop(container: BrowserContainer, interval_sec: int) -> None:
    """
    Фоновая очистка рантайма: истёкшие lease, idle-контексты и старые артефакты.

    Запускается на старте сервиса, потому что sweep/eviction иначе срабатывают только
    в момент acquire — без трафика брошенные warm-сессии не освобождались бы.
    """
    while True:
        await asyncio.sleep(interval_sec)
        try:
            await container.browser_runtime.reap_once()
        except Exception as exc:
            # Reaper обязан пережить транзиентные сбои Playwright/FS и продолжить цикл:
            # одна неудачная уборка не должна останавливать фоновую очистку рантайма.
            logger.error(
                "browser.reaper.failed",
                **{"exception.type": type(exc).__name__},
                error=str(exc),
            )


async def on_startup(app: FastAPI, container: BrowserContainer, settings: BrowserSettings) -> None:
    _ = app
    await container.redis_client.connect()
    logger.info("browser.redis.connected")
    interval_sec = settings.browser.reaper_interval_sec
    container.reaper_task = run_with_log_context(
        _reaper_loop(container, interval_sec),
        name="browser.reaper",
        background_kind="polling",
    )
    logger.info("browser.reaper.started", interval_sec=interval_sec)


async def on_shutdown(app: FastAPI, container: BrowserContainer) -> None:
    _ = app
    task = container.reaper_task
    if task is not None:
        _ = task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        container.reaper_task = None
        logger.info("browser.reaper.stopped")
    stopped = await container.stop_browser_runtime()
    if stopped:
        logger.info("BrowserRuntimeFacade остановлен")
    await container.redis_client.close()
    logger.info("browser.redis.closed")


app = create_service_app(
    service_name="browser",
    settings_class=BrowserSettings,
    get_container=get_browser_container,
    routers=[
        browser_control_router,
        browser_crawl_fetch_router,
        browser_mcp_router,
        browser_health_router,
    ],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    cors_origins=["*"],
    title="Platform Browser Runtime",
    description="Playwright + CDP (Lightpanda / Chromium)",
    version="1.0.0",
    api_version="v1",
    include_crud_routers=False,
    documentation_gateway_prefix="browser",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("browser", "apps.browser.main:app", get_browser_settings())

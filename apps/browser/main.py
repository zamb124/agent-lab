"""
Сервис browser: Browser Runtime v1, health, минимальный control-plane HTTP.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

from apps.browser.api.control import router as browser_control_router
from apps.browser.api.crawl_fetch import router as browser_crawl_fetch_router
from apps.browser.api.health import router as browser_health_router
from apps.browser.api.mcp import router as browser_mcp_router
from apps.browser.config import BrowserSettings, get_browser_settings
from apps.browser.di import BrowserDi
from apps.browser.services.runtime_facade import BrowserRuntimeFacade
from core.app import create_service_app
from core.clients.redis_client import RedisClient
from core.di import recipe
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


async def _reaper_loop(browser_runtime: BrowserRuntimeFacade, interval_sec: int) -> None:
    """
    Фоновая очистка рантайма: истёкшие lease, idle-контексты и старые артефакты.

    Запускается на старте сервиса, потому что sweep/eviction иначе срабатывают только
    в момент acquire — без трафика брошенные warm-сессии не освобождались бы.
    """
    while True:
        await asyncio.sleep(interval_sec)
        try:
            await browser_runtime.reap_once()
        except Exception as exc:
            # Reaper обязан пережить транзиентные сбои Playwright/FS и продолжить цикл:
            # одна неудачная уборка не должна останавливать фоновую очистку рантайма.
            logger.error(
                "browser.reaper.failed",
                **{"exception.type": type(exc).__name__},
                error=str(exc),
            )


async def browser_reaper(
    browser_runtime: BrowserRuntimeFacade,
    settings: BrowserSettings,
    redis_client: RedisClient,
) -> AsyncIterator[None]:
    await redis_client.connect()
    logger.info("browser.redis.connected")
    interval_sec = settings.browser.reaper_interval_sec
    task = run_with_log_context(
        _reaper_loop(browser_runtime, interval_sec),
        name="browser.reaper",
        background_kind="polling",
    )
    logger.info("browser.reaper.started", interval_sec=interval_sec)
    try:
        yield
    finally:
        _ = task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("browser.reaper.stopped")


app = create_service_app(
    "browser",
    BrowserSettings,
    BrowserDi,
    database="shared_url",
    lifecycle=(recipe(browser_reaper),),
    routers=[
        browser_control_router,
        browser_crawl_fetch_router,
        browser_mcp_router,
        browser_health_router,
    ],
    cors_origins=["*"],
    title="Platform Browser Runtime",
    description="Playwright + CDP (Lightpanda / Chromium)",
    version="1.0.0",
    api_version="v1",
    documentation_gateway_prefix="browser",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("browser", "apps.browser.main:app", get_browser_settings())

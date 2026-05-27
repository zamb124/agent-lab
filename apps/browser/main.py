"""
Сервис browser: Browser Runtime v1, health, минимальный control-plane HTTP.
"""

from fastapi import FastAPI

from apps.browser.api.control import router as browser_control_router
from apps.browser.api.mcp import router as browser_mcp_router
from apps.browser.config import BrowserSettings, get_browser_settings
from apps.browser.container import BrowserContainer, get_browser_container
from core.app import create_service_app
from core.logging import get_logger

logger = get_logger(__name__)


async def on_shutdown(app: FastAPI, container: BrowserContainer) -> None:
    _ = app
    stopped = await container.stop_browser_runtime()
    if stopped:
        logger.info("BrowserRuntimeFacade остановлен")


app = create_service_app(
    service_name="browser",
    settings_class=BrowserSettings,
    get_container=get_browser_container,
    routers=[browser_control_router, browser_mcp_router],
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

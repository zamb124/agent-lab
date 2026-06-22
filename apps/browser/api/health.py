"""
Health-проба готовности по CDP для сервиса browser.

`GET /browser/api/v1/health/cdp` проверяет, что app-контейнер реально может работать
с Chromium (CDP endpoint жив и подключение установлено). Используется как readiness
probe: пока Chromium недоступен/перезапускается, под выводится из эндпоинтов Service,
а не отдаёт ошибки навигации.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter, Response
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, ConfigDict

from apps.browser.dependencies import ContainerDep
from core.logging import get_logger

router = APIRouter(prefix="/health", tags=["browser-health"])

logger = get_logger(__name__)


class CdpHealthResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    cdp_connected: bool
    endpoint_key: str


@router.get("/cdp", response_model=CdpHealthResponse)
async def health_cdp(container: ContainerDep, response: Response) -> CdpHealthResponse:
    runtime = container.browser_runtime
    endpoint_key = runtime.settings.default_endpoint_key
    cdp_url = runtime.settings.cdp_urls_by_endpoint[endpoint_key]
    try:
        browser = await runtime.pool.acquire_browser(endpoint_key, cdp_url)
        connected = browser.is_connected()
    except PlaywrightError as exc:
        logger.warning("browser.health.cdp_unavailable", endpoint_key=endpoint_key, error=str(exc))
        response.status_code = 503
        return CdpHealthResponse(cdp_connected=False, endpoint_key=endpoint_key)
    if not connected:
        response.status_code = 503
    return CdpHealthResponse(cdp_connected=connected, endpoint_key=endpoint_key)

"""HTTP client for browser one-shot crawl fetch."""

from __future__ import annotations

from typing import Literal

from core.clients.browser.crawl_fetch_types import (
    BrowserCrawlFetchRequest,
    BrowserCrawlFetchResponse,
)
from core.clients.service_client import ServiceClient


class BrowserFetchClient:
    def __init__(self, service_client: ServiceClient) -> None:
        self._client: ServiceClient = service_client

    async def fetch_html(
        self,
        url: str,
        *,
        timeout_ms: int,
        service_timeout_seconds: float,
        locale: str | None = None,
        wait_selector: str | None = None,
        html_capture: Literal["flat", "dsd"] = "flat",
        block_resource_types: list[str] | None = None,
    ) -> BrowserCrawlFetchResponse:
        body = BrowserCrawlFetchRequest(
            url=url,
            navigation_timeout_ms=timeout_ms,
            locale=locale,
            wait_selector=wait_selector,
            html_capture=html_capture,
            block_resource_types=(
                block_resource_types
                if block_resource_types is not None
                else ["image", "media", "font", "stylesheet"]
            ),
        )
        response = await self._client.post(
            "browser",
            "/browser/api/v1/control/crawl/fetch",
            json=body.model_dump(mode="json"),
            timeout=service_timeout_seconds,
        )
        return BrowserCrawlFetchResponse.model_validate(response)

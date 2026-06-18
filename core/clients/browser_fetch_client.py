"""HTTP client for browser one-shot crawl fetch."""

from __future__ import annotations

from apps.browser.contracts.crawl_fetch_types import (
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
    ) -> BrowserCrawlFetchResponse:
        body = BrowserCrawlFetchRequest(
            url=url,
            navigation_timeout_ms=timeout_ms,
        )
        response = await self._client.post(
            "browser",
            "/browser/api/v1/control/crawl/fetch",
            json=body.model_dump(mode="json"),
            timeout=service_timeout_seconds,
        )
        return BrowserCrawlFetchResponse.model_validate(response)

"""Browser fetch client timeout contract."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.clients.browser_fetch_client import BrowserFetchClient

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fetch_html_passes_service_timeout_to_browser_post() -> None:
    service_client = MagicMock()
    service_client.post = AsyncMock(
        return_value={
            "final_url": "https://example.com/",
            "status_code": 200,
            "html": "<html><body>Example</body></html>",
            "anti_bot_signals": {},
        }
    )
    client = BrowserFetchClient(service_client)
    response = await client.fetch_html(
        "https://example.com/",
        timeout_ms=20_000,
        service_timeout_seconds=120.0,
    )
    assert response.final_url == "https://example.com/"
    service_client.post.assert_awaited_once_with(
        "browser",
        "/browser/api/v1/control/crawl/fetch",
        json={
            "url": "https://example.com/",
            "wait_policy": "domcontentloaded",
            "navigation_timeout_ms": 20_000,
            "block_resource_types": ["image", "media", "font", "stylesheet"],
        },
        timeout=120.0,
    )

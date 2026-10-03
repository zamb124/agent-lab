"""Browser crawl fetch endpoint: concurrency limit and request defaults."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.authz.models import AuthzObject
from core.clients.browser.crawl_fetch_types import BrowserCrawlFetchRequest
from core.clients.browser_fetch_client import BrowserFetchClient
from core.websocket import WsCommandError

pytestmark = pytest.mark.unit


class _StubAuthz:
    async def require_can_view(self, obj: AuthzObject) -> None:
        _ = obj


@pytest.mark.asyncio
async def test_crawl_fetch_returns_429_when_concurrency_limit_exceeded() -> None:
    import apps.browser.api.crawl_fetch as crawl_fetch_module

    class _BlockedSemaphore:
        async def acquire(self) -> None:
            raise TimeoutError

        def release(self) -> None:
            return None

    di = SimpleNamespace(
        authz_service=_StubAuthz(),
        browser_runtime=SimpleNamespace(
            settings=SimpleNamespace(crawl_fetch_max_inflight=2),
        ),
    )

    async def _wait_for_timeout(coro: object, /, **kwargs: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise TimeoutError

    with patch.object(crawl_fetch_module, "_crawl_fetch_semaphore", return_value=_BlockedSemaphore()):
        with patch.object(crawl_fetch_module.asyncio, "wait_for", side_effect=_wait_for_timeout):
            with pytest.raises(WsCommandError) as exc_info:
                await crawl_fetch_module.crawl_fetch(
                    BrowserCrawlFetchRequest(url="https://example.com/page"),
                    di,  # pyright: ignore[reportArgumentType]
                )

    assert exc_info.value.code == "rate_limited"
    assert "concurrency limit" in exc_info.value.detail


@pytest.mark.asyncio
async def test_browser_fetch_client_uses_networkidle_wait_policy() -> None:
    captured: list[dict[str, object]] = []

    class _Client:
        async def post(
            self,
            service: str,
            path: str,
            *,
            json: dict[str, object],
            timeout: float,
        ) -> dict[str, object]:
            captured.append({"service": service, "path": path, "json": json, "timeout": timeout})
            return {
                "final_url": json["url"],
                "status_code": 200,
                "html": "<html><body>ok</body></html>",
                "anti_bot_signals": {},
            }

    client = BrowserFetchClient(_Client())  # pyright: ignore[reportArgumentType]
    _ = await client.fetch_html("https://example.com/page", timeout_ms=5000, service_timeout_seconds=30.0)

    assert len(captured) == 1
    body = captured[0]["json"]
    assert body["wait_policy"] == "domcontentloaded"
    parsed = BrowserCrawlFetchRequest.model_validate(body)
    assert set(parsed.block_resource_types) == {"image", "media", "font", "stylesheet"}

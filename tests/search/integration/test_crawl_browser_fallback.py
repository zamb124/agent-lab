"""Browser fallback for crawl fetch when HTTP extraction is too short."""

from __future__ import annotations

import importlib
import os
import uuid

import pytest
from aiohttp import web
from httpx import ASGITransport, AsyncClient

from apps.search.config import get_search_settings
from apps.search.services.crawl.fetch_service import CrawlFetchService
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.service_client import ServiceClient
from tests.browser.e2e_step_metrics import e2e_lightpanda_cdp_url, e2e_lightpanda_enabled
from tests.fixtures.aiohttp_ephemeral import tcp_site_assigned_port

pytestmark = [pytest.mark.integration, pytest.mark.timeout(180, func_only=True)]


_JS_PAGE_HTML = """<!DOCTYPE html>
<html><head><title>JS crawl fixture</title></head>
<body><div id="content"></div>
<script>
document.getElementById('content').textContent =
  'Runet browser fallback fixture paragraph with enough extractable text for crawl indexing pipeline validation.';
</script>
</body></html>"""


async def _start_js_fixture_server() -> tuple[str, web.AppRunner]:
    async def _handler(_request: web.Request) -> web.Response:
        return web.Response(text=_JS_PAGE_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/", _handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = tcp_site_assigned_port(site)
    return f"http://127.0.0.1:{port}/", runner


def _build_browser_app(*, cdp_url: str, artifacts_dir: str) -> object:
    os.environ["BROWSER__CDP_URL"] = cdp_url
    os.environ["BROWSER__ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("SERVER__BROWSER_SERVICE_URL", "http://testserver")

    from apps.browser.config import reset_browser_settings
    from apps.browser.container import reset_browser_container

    reset_browser_settings()
    reset_browser_container()

    import apps.browser.main as browser_main

    return importlib.reload(browser_main).app


@pytest.mark.asyncio
async def test_http_short_then_browser_fallback_succeeds(search_system_context) -> None:
    _ = search_system_context
    if not e2e_lightpanda_enabled():
        pytest.skip("Включите BROWSER__E2E_LIGHTPANDA=1 для browser crawl fallback e2e")
    cdp = e2e_lightpanda_cdp_url()
    if not cdp:
        pytest.skip("Укажите BROWSER__E2E_LIGHTPANDA_CDP_URL или BROWSER__CDP_URL")

    page_url, runner = await _start_js_fixture_server()
    uid = uuid.uuid4().hex
    browser_app = _build_browser_app(cdp_url=cdp, artifacts_dir=f"artifacts/crawl_fallback_{uid}")

    try:
        async with browser_app.router.lifespan_context(browser_app):
            transport = ASGITransport(app=browser_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as browser_http:
                service_client = ServiceClient()
                original_post = service_client.post

                async def _browser_local_post(service: str, path: str, **kwargs: object) -> object:
                    if service == "browser":
                        response = await browser_http.post(path, json=kwargs.get("json"))
                        if response.status_code >= 400:
                            raise RuntimeError(response.text)
                        return response.json()
                    return await original_post(service, path, **kwargs)

                service_client.post = _browser_local_post  # pyright: ignore[reportAttributeAccessIssue]
                fetch_service = CrawlFetchService(
                    browser_fetch_client=BrowserFetchClient(service_client),
                    browser_fetch_timeout_seconds=get_search_settings().crawl.browser_fetch_timeout_seconds,
                )
                result = await fetch_service.fetch_markdown(
                    page_url,
                    timeout_seconds=get_search_settings().crawl.http_timeout_seconds,
                    min_extract_chars=80,
                    browser_fallback_enabled=True,
                )
                assert result.fetch_transport == "browser"
                assert "browser fallback fixture" in result.markdown.lower()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_browser_fallback_disabled_raises_without_browser(search_system_context) -> None:
    _ = search_system_context
    page_url, runner = await _start_js_fixture_server()
    try:
        fetch_service = CrawlFetchService(
            browser_fetch_client=BrowserFetchClient(ServiceClient()),
            browser_fetch_timeout_seconds=get_search_settings().crawl.browser_fetch_timeout_seconds,
        )
        with pytest.raises(ValueError, match="extracted text too short"):
            await fetch_service.fetch_markdown(
                page_url,
                timeout_seconds=get_search_settings().crawl.http_timeout_seconds,
                min_extract_chars=80,
                browser_fallback_enabled=False,
            )
    finally:
        await runner.cleanup()

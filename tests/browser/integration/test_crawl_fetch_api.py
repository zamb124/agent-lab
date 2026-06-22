"""Browser one-shot crawl fetch API (real Playwright when CDP is configured)."""

from __future__ import annotations

import importlib
import os

import pytest
from httpx import ASGITransport, AsyncClient

from tests.browser.e2e_step_metrics import e2e_lightpanda_cdp_url, e2e_lightpanda_enabled

pytestmark = [pytest.mark.integration, pytest.mark.xdist_group("browser_cdp")]


def _build_browser_app(*, cdp_url: str) -> object:
    os.environ["BROWSER__CDP_URL"] = cdp_url

    from apps.browser.config import reset_browser_settings
    from apps.browser.container import reset_browser_container

    reset_browser_settings()
    reset_browser_container()

    import apps.browser.main as browser_main

    return importlib.reload(browser_main).app


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(180, func_only=True)
async def test_crawl_fetch_returns_html_from_example_com() -> None:
    if not e2e_lightpanda_enabled():
        pytest.skip("Включите BROWSER__E2E_LIGHTPANDA=1 для browser crawl fetch e2e")
    cdp = e2e_lightpanda_cdp_url()
    if not cdp:
        pytest.skip("Укажите BROWSER__E2E_LIGHTPANDA_CDP_URL или BROWSER__CDP_URL")

    app = _build_browser_app(cdp_url=cdp)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/browser/api/v1/control/crawl/fetch",
                json={
                    "url": "https://example.com",
                    "wait_policy": "domcontentloaded",
                    "navigation_timeout_ms": 60_000,
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert "example.com" in payload["final_url"]
            assert payload["status_code"] == 200
            assert isinstance(payload["html"], str)
            assert "Example Domain" in payload["html"]
            assert isinstance(payload["anti_bot_signals"], dict)

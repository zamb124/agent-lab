"""
E2E: Browser MCP HTTP API (JSON-RPC 2.0) по реальному CDP (Lightpanda).

Проверяем MCP контракт:
- initialize -> Mcp-Session-Id header
- tools/list -> содержит browser tools
- tools/call -> create_session / navigate / observe / close_session
"""

from __future__ import annotations

import importlib
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pathlib import Path

from tests.browser.e2e_step_metrics import e2e_lightpanda_cdp_url, e2e_lightpanda_enabled

pytestmark = pytest.mark.xdist_group("browser_cdp")


def _build_browser_app(*, cdp_url: str, artifacts_dir: str) -> object:
    os.environ["BROWSER__CDP_URL"] = cdp_url
    os.environ["BROWSER__ARTIFACTS_DIR"] = artifacts_dir

    from apps.browser.config import reset_browser_settings
    from apps.browser.container import reset_browser_container

    reset_browser_settings()
    reset_browser_container()

    import apps.browser.main as browser_main

    return importlib.reload(browser_main).app


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(300, func_only=True)
async def test_mcp_http_api_initialize_list_and_call() -> None:
    if not e2e_lightpanda_enabled():
        pytest.skip("Включите BROWSER__E2E_LIGHTPANDA=1 для явного e2e Lightpanda")
    cdp = e2e_lightpanda_cdp_url()
    if not cdp:
        pytest.skip("Укажите BROWSER__E2E_LIGHTPANDA_CDP_URL (предпочтительно) или BROWSER__CDP_URL")

    uid = uuid.uuid4().hex
    app = _build_browser_app(
        cdp_url=cdp,
        artifacts_dir=f"artifacts/browser_e2e_http_mcp_{uid}",
    )

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            # initialize
            r0 = await ac.post(
                "/browser/api/v1/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            assert r0.status_code == 200, r0.text
            assert "Mcp-Session-Id" in r0.headers
            init_body = r0.json()
            assert init_body["jsonrpc"] == "2.0"
            assert init_body["id"] == 1
            assert init_body["result"]["protocolVersion"]

            mcp_sid = r0.headers["Mcp-Session-Id"]

            # tools/list
            r1 = await ac.post(
                "/browser/api/v1/mcp",
                headers={"Mcp-Session-Id": mcp_sid},
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            assert r1.status_code == 200, r1.text
            tools_body = r1.json()
            tools = tools_body["result"]["tools"]
            names = {t["name"] for t in tools}
            assert "browser_create_session" in names
            assert "browser_observe" in names
            assert "browser_close_session" in names

            # tools/call: create session
            session_id = f"sess-mcp-{uid}"
            r2 = await ac.post(
                "/browser/api/v1/mcp",
                headers={"Mcp-Session-Id": mcp_sid},
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "browser_create_session",
                        "arguments": {
                            "session_id": session_id,
                            "page_mode": "crawl",
                            "timeout_ms": 60_000,
                            "session_mode": "warm",
                            "context": {"page_mode": "crawl"},
                        },
                    },
                },
            )
            assert r2.status_code == 200, r2.text
            create_result = r2.json()["result"]
            assert create_result["isError"] is False

            # tools/call: navigate
            r3 = await ac.post(
                "/browser/api/v1/mcp",
                headers={"Mcp-Session-Id": mcp_sid},
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "browser_navigate",
                        "arguments": {
                            "session_id": session_id,
                            "url": "https://example.com",
                            "wait_policy": "domcontentloaded",
                            "screenshot": False,
                            "snapshot": False,
                            "capture_pdf": False,
                            "navigation_timeout_ms": 60_000,
                        },
                    },
                },
            )
            assert r3.status_code == 200, r3.text
            nav_result = r3.json()["result"]
            assert nav_result["isError"] is False

            # tools/call: observe
            r4 = await ac.post(
                "/browser/api/v1/mcp",
                headers={"Mcp-Session-Id": mcp_sid},
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "browser_observe",
                        "arguments": {"session_id": session_id},
                    },
                },
            )
            assert r4.status_code == 200, r4.text
            obs_result = r4.json()["result"]
            assert obs_result["isError"] is False
            obs_text = obs_result["content"][0]["text"]
            assert isinstance(obs_text, str) and obs_text

            # tools/call: close session
            r5 = await ac.post(
                "/browser/api/v1/mcp",
                headers={"Mcp-Session-Id": mcp_sid},
                json={
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "browser_close_session", "arguments": {"session_id": session_id}},
                },
            )
            assert r5.status_code == 200, r5.text
            close_result = r5.json()["result"]
            assert close_result["isError"] is False

            # Артефакты runtime: service-side лог вызовов по шагам.
            events_dir = Path(f"artifacts/browser_e2e_http_mcp_{uid}") / "sessions" / session_id / "events"
            assert events_dir.exists(), f"events_dir отсутствует: {events_dir}"
            events = sorted(p for p in events_dir.iterdir() if p.suffix == ".json")
            assert len(events) >= 4, f"Ожидались event artifacts, найдено: {len(events)}"


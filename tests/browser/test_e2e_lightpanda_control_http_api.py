"""
E2E: Browser Control HTTP API по реальному CDP (Lightpanda).

Цель: проверить «все варианты обращения» к browser runtime через публичный HTTP:
- создание control-сессии
- navigate (fetch) с разными wait_policy и артефактами
- observe (visibility/html/dom_diff/listeners/ax)
- legacy action явно запрещён без in-process исполнения кода
- закрытие сессии

Тест запускается только при явном флаге BROWSER__E2E_LIGHTPANDA=1 и наличии CDP URL.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

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
async def test_control_http_api_full_flow() -> None:
    if not e2e_lightpanda_enabled():
        pytest.skip("Включите BROWSER__E2E_LIGHTPANDA=1 для явного e2e Lightpanda")
    cdp = e2e_lightpanda_cdp_url()
    if not cdp:
        pytest.skip("Укажите BROWSER__E2E_LIGHTPANDA_CDP_URL (предпочтительно) или BROWSER__CDP_URL")

    uid = uuid.uuid4().hex
    artifacts_dir = f"artifacts/browser_e2e_http_control_{uid}"
    app = _build_browser_app(cdp_url=cdp, artifacts_dir=artifacts_dir)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            # создаём session
            create_body = {
                "session_id": f"sess-http-{uid}",
                "run_id": f"run-http-{uid}",
                "task_id": f"task-http-{uid}",
                "page_mode": "crawl",
                "timeout_ms": 60_000,
                "session_mode": "warm",
                "context": {
                    "page_mode": "crawl",
                    "emulate_locale_timezone_via_cdp": False,
                },
            }
            r = await ac.post("/browser/api/v1/control/sessions", json=create_body)
            assert r.status_code == 200, r.text
            created = r.json()
            assert created["session_id"] == create_body["session_id"]
            assert created["endpoint_key"]
            assert isinstance(created["features"], dict)

            session_id = created["session_id"]

            # navigate: domcontentloaded, screenshot + snapshot
            nav_body = {
                "url": "https://example.com",
                "wait_policy": "domcontentloaded",
                "screenshot": True,
                "snapshot": True,
                "capture_pdf": False,
                "navigation_timeout_ms": 60_000,
            }
            r2 = await ac.post(f"/browser/api/v1/control/sessions/{session_id}/navigate", json=nav_body)
            assert r2.status_code == 200, r2.text
            nav = r2.json()
            assert nav["status_code"] == 200
            assert "example.com" in (nav["final_url"] or "")
            assert isinstance(nav["response_headers"], dict)
            assert isinstance(nav["screenshot_ref"], str) and nav["screenshot_ref"]
            assert isinstance(nav["snapshot_ref"], str) and nav["snapshot_ref"]
            assert nav["pdf_ref"] is None

            shot_path = Path(nav["screenshot_ref"])
            snap_path = Path(nav["snapshot_ref"])
            assert shot_path.exists()
            assert snap_path.exists()

            # observe: visibility + html + dom_diff (первый раз html_changed=True, второй — False)
            obs_body = {
                "budget": 50,
                "include_html": True,
                "include_visibility": True,
                "include_ax": True,
                "include_listeners": True,
                "include_dom_diff": True,
            }
            ro = await ac.post(f"/browser/api/v1/control/sessions/{session_id}/observe", json=obs_body)
            assert ro.status_code == 200, ro.text
            o1 = ro.json()
            assert o1["session_id"] == session_id
            assert isinstance(o1.get("html"), str)
            assert isinstance(o1.get("html_fingerprint_sha256"), str)
            assert o1.get("html_changed") in (True, False)
            assert "visibility" in o1
            assert "accessibility" in o1
            assert "dom_event_listeners" in o1
            assert "visibility_diff" in o1

            await asyncio.sleep(0.05)
            ro2 = await ac.post(f"/browser/api/v1/control/sessions/{session_id}/observe", json=obs_body)
            assert ro2.status_code == 200, ro2.text
            o2 = ro2.json()
            assert o2["html_fingerprint_sha256"] == o1["html_fingerprint_sha256"]
            assert o2["html_changed"] is False

            # legacy action: произвольный in-process код запрещён
            ra = await ac.post(
                f"/browser/api/v1/control/sessions/{session_id}/action",
                json={"code": "print(page.url)", "timeout_ms": 30_000},
            )
            assert ra.status_code == 501, ra.text
            detail = ra.json()["detail"]
            assert detail["code"] == "browser_action_disabled"

            # удаляем session
            rd = await ac.delete(f"/browser/api/v1/control/sessions/{session_id}")
            assert rd.status_code == 200, rd.text
            assert rd.json()["status"] == "closed"

            # навигация после удаления → 404
            r404 = await ac.post(
                f"/browser/api/v1/control/sessions/{session_id}/navigate",
                json={"url": "https://example.com"},
            )
            assert r404.status_code == 404


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(120, func_only=True)
async def test_control_http_api_validation_page_mode_mismatch() -> None:
    if not e2e_lightpanda_enabled():
        pytest.skip("Включите BROWSER__E2E_LIGHTPANDA=1 для явного e2e Lightpanda")
    cdp = e2e_lightpanda_cdp_url()
    if not cdp:
        pytest.skip("Укажите BROWSER__E2E_LIGHTPANDA_CDP_URL (предпочтительно) или BROWSER__CDP_URL")

    uid = uuid.uuid4().hex
    app = _build_browser_app(
        cdp_url=cdp,
        artifacts_dir=f"artifacts/browser_e2e_http_control_{uid}",
    )

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            body = {
                "session_id": f"sess-bad-{uid}",
                "page_mode": "crawl",
                "context": {
                    "page_mode": "interactive",
                    "emulate_locale_timezone_via_cdp": False,
                },
            }
            r = await ac.post("/browser/api/v1/control/sessions", json=body)
            assert r.status_code == 422

"""Временный скриншот-проход для UI-ревизии (не часть регресса).

Прогон:
    uv run pytest tests/ui/e2e/test_ui_audit_screenshots.py -q -n 0

Пишет PNG в /tmp/ui_audit_shots/<svc>/<route>_<viewport>.png.
Авторизованные SPA живут на company subdomain воркера: ui-gwN.lvh.me.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.async_api import Page

from tests.ui.e2e_worker import ui_e2e_subdomain
from tests.ui.harness import ui_e2e_use_lvh_me

OUT = Path("/tmp/ui_audit_shots")
_HOST = "lvh.me" if ui_e2e_use_lvh_me() else "localhost"
APEX = f"http://{_HOST}:9004"
CO = f"http://{ui_e2e_subdomain()}.{_HOST}"

# (svc, url, shell_selector) — авторизованные маршруты worker-компании gw0.
ROUTES: list[tuple[str, str, str]] = [
    ("frontend", f"{CO}:9004/dashboard", "frontend-app"),
    ("frontend", f"{CO}:9004/services", "frontend-app"),
    ("frontend", f"{CO}:9004/search", "frontend-app"),
    ("frontend", f"{CO}:9004/namespaces", "frontend-app"),
    ("frontend", f"{CO}:9004/team", "frontend-app"),
    ("frontend", f"{CO}:9004/billing", "frontend-app"),
    ("frontend", f"{CO}:9004/settings", "frontend-app"),
    ("crm", f"{CO}:9003/crm/notes", "crm-app"),
    ("crm", f"{CO}:9003/crm/entities", "crm-app"),
    ("crm", f"{CO}:9003/crm/graph", "crm-app"),
    ("crm", f"{CO}:9003/crm/tasks", "crm-app"),
    ("crm", f"{CO}:9003/crm/namespaces", "crm-app"),
    ("crm", f"{CO}:9003/crm/settings", "crm-app"),
    ("flows", f"{CO}:9001/flows/example_react", "flows-app"),
    ("flows", f"{CO}:9001/flows/example_react/editor", "flows-app"),
    ("flows", f"{CO}:9001/flows/skills", "flows-app"),
    ("flows", f"{CO}:9001/flows/services", "flows-app"),
    ("rag", f"{CO}:9002/rag/search", "rag-app"),
    ("rag", f"{CO}:9002/rag/settings", "rag-app"),
    ("rag", f"{CO}:9002/rag/namespaces/default", "rag-app"),
    ("sync", f"{CO}:9005/sync/", "sync-app"),
    ("sync", f"{CO}:9005/sync/calls/scheduled", "sync-app"),
    ("sync", f"{CO}:9005/sync/settings", "sync-app"),
    ("office", f"{CO}:9008/documents/recent", "office-app"),
    ("office", f"{CO}:9008/documents/catalogs", "office-app"),
    ("worktracker", f"{CO}:9021/worktracker/my", "worktracker-app"),
    ("worktracker", f"{CO}:9021/worktracker/board", "worktracker-app"),
    ("worktracker", f"{CO}:9021/worktracker/queues", "worktracker-app"),
    ("wiki", f"{CO}:9023/wiki/", "wiki-app"),
    ("wiki", f"{CO}:9023/wiki/search", "wiki-app"),
    ("stock", f"{CO}:9026/stock/products", "stock-app"),
    ("stock", f"{CO}:9026/stock/transfers", "stock-app"),
    ("stock", f"{CO}:9026/stock/locations", "stock-app"),
    ("stock", f"{CO}:9026/stock/valuation", "stock-app"),
    ("litserve", f"{CO}:9014/litserve/", "litserve-app"),
]

PUBLIC_ROUTES: list[tuple[str, str, str]] = [
    ("frontend", f"{APEX}/", "frontend-app"),
    ("frontend", f"{APEX}/login", "frontend-app"),
    ("frontend", f"{APEX}/products/agents", "frontend-app"),
]

DARK_SPOT_CHECK = [
    ("frontend", f"{CO}:9004/dashboard", "frontend-app"),
    ("crm", f"{CO}:9003/crm/notes", "crm-app"),
    ("flows", f"{CO}:9001/flows/example_react/editor", "flows-app"),
    ("sync", f"{CO}:9005/sync/", "sync-app"),
]

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1024},
    "mobile": {"width": 390, "height": 844},
}


def _slug(url: str) -> str:
    path = re.sub(r"^https?://[^/]+", "", url).strip("/") or "root"
    return re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")


async def _shot(page: Page, svc: str, url: str, shell: str, tag: str) -> None:
    (OUT / svc).mkdir(parents=True, exist_ok=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_selector(shell, state="attached", timeout=8_000)
    except Exception:
        pass
    await page.wait_for_timeout(1_800)
    await page.screenshot(path=str(OUT / svc / f"{_slug(url)}_{tag}.png"), full_page=False)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "route", ROUTES, ids=[f"{svc}-{_slug(url)}" for svc, url, _ in ROUTES]
)
async def test_ui_audit_desktop(ui_page_system: Page, route: tuple[str, str, str]) -> None:
    svc, url, shell = route
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["desktop"])
    await _shot(page, svc, url, shell, "desktop")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "route", ROUTES, ids=[f"{svc}-{_slug(url)}" for svc, url, _ in ROUTES]
)
async def test_ui_audit_mobile(ui_page_system: Page, route: tuple[str, str, str]) -> None:
    svc, url, shell = route
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["mobile"])
    await _shot(page, svc, url, shell, "mobile")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "route", PUBLIC_ROUTES, ids=[f"{svc}-{_slug(url)}" for svc, url, _ in PUBLIC_ROUTES]
)
async def test_ui_audit_public(ui_page_system: Page, route: tuple[str, str, str]) -> None:
    """Публичные маршруты apex (landing/login/products)."""
    svc, url, shell = route
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["desktop"])
    await _shot(page, svc, url, shell, "desktop")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "route", DARK_SPOT_CHECK, ids=[f"{svc}-{_slug(url)}" for svc, url, _ in DARK_SPOT_CHECK]
)
async def test_ui_audit_dark(ui_page_system: Page, route: tuple[str, str, str]) -> None:
    """Spot-check dark theme на авторизованных маршрутах."""
    svc, url, shell = route
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["desktop"])
    await page.add_init_script(
        "() => { try { window.localStorage.setItem('platform_theme', 'dark'); } catch (_) {} }"
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await page.evaluate(
        "() => { document.documentElement.setAttribute('data-theme', 'dark');"
        " document.documentElement.removeAttribute('data-platform-theme-lock'); }"
    )
    await page.wait_for_timeout(2_500)
    await _shot(page, svc, url, shell, "dark")

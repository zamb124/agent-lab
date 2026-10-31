"""Временный скриншот-проход для UI-ревизии (не часть регресса).

Прогон:
    uv run pytest tests/ui/e2e/test_ui_audit_screenshots.py -q -n 0

Пишет PNG в /tmp/ui_audit_shots/<svc>/<route>_<viewport>.png.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.async_api import Page

OUT = Path("/tmp/ui_audit_shots")

# (svc, url, shell_selector) — representative routes за авторизованным владельцем worker-компании.
ROUTES: list[tuple[str, str, str]] = [
    ("frontend", "http://localhost:9004/", "frontend-app"),
    ("frontend", "http://localhost:9004/dashboard", "frontend-app"),
    ("frontend", "http://localhost:9004/services", "frontend-app"),
    ("frontend", "http://localhost:9004/search", "frontend-app"),
    ("frontend", "http://localhost:9004/namespaces", "frontend-app"),
    ("frontend", "http://localhost:9004/team", "frontend-app"),
    ("frontend", "http://localhost:9004/billing", "frontend-app"),
    ("frontend", "http://localhost:9004/settings", "frontend-app"),
    ("crm", "http://localhost:9003/crm/notes", "crm-app"),
    ("crm", "http://localhost:9003/crm/entities", "crm-app"),
    ("crm", "http://localhost:9003/crm/graph", "crm-app"),
    ("crm", "http://localhost:9003/crm/tasks", "crm-app"),
    ("crm", "http://localhost:9003/crm/namespaces", "crm-app"),
    ("crm", "http://localhost:9003/crm/settings", "crm-app"),
    ("flows", "http://localhost:9001/flows/", "flows-app"),
    ("flows", "http://localhost:9001/flows/example_react", "flows-app"),
    ("flows", "http://localhost:9001/flows/example_react/editor", "flows-app"),
    ("flows", "http://localhost:9001/flows/skills", "flows-app"),
    ("rag", "http://localhost:9002/rag/search", "rag-app"),
    ("rag", "http://localhost:9002/rag/settings", "rag-app"),
    ("rag", "http://localhost:9002/rag/namespaces/default", "rag-app"),
    ("sync", "http://localhost:9005/sync/", "sync-app"),
    ("sync", "http://localhost:9005/sync/calls/scheduled", "sync-app"),
    ("sync", "http://localhost:9005/sync/settings", "sync-app"),
    ("office", "http://localhost:9008/documents/recent", "office-app"),
    ("office", "http://localhost:9008/documents/catalogs", "office-app"),
    ("worktracker", "http://localhost:9021/worktracker/my", "worktracker-app"),
    ("worktracker", "http://localhost:9021/worktracker/board", "worktracker-app"),
    ("worktracker", "http://localhost:9021/worktracker/queues", "worktracker-app"),
    ("wiki", "http://localhost:9023/wiki/", "wiki-app"),
    ("wiki", "http://localhost:9023/wiki/search", "wiki-app"),
    ("stock", "http://localhost:9026/stock/products", "stock-app"),
    ("stock", "http://localhost:9026/stock/transfers", "stock-app"),
    ("stock", "http://localhost:9026/stock/locations", "stock-app"),
    ("stock", "http://localhost:9026/stock/valuation", "stock-app"),
    ("litserve", "http://localhost:9014/litserve/", "litserve-app"),
]

DARK_SPOT_CHECK = [
    ("frontend", "http://localhost:9004/dashboard", "frontend-app"),
    ("crm", "http://localhost:9003/crm/notes", "crm-app"),
    ("flows", "http://localhost:9001/flows/example_react/editor", "flows-app"),
    ("sync", "http://localhost:9005/sync/", "sync-app"),
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
        await page.wait_for_selector(shell, state="attached", timeout=10_000)
    except Exception:
        pass
    await page.wait_for_timeout(2_500)
    await page.screenshot(path=str(OUT / svc / f"{_slug(url)}_{tag}.png"), full_page=False)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(600)
async def test_ui_audit_desktop(ui_page_system: Page) -> None:
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["desktop"])
    for svc, url, shell in ROUTES:
        await _shot(page, svc, url, shell, "desktop")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(600)
async def test_ui_audit_mobile(ui_page_system: Page) -> None:
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["mobile"])
    for svc, url, shell in ROUTES:
        await _shot(page, svc, url, shell, "mobile")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_ui_audit_dark(ui_page_system: Page) -> None:
    page = ui_page_system
    await page.set_viewport_size(VIEWPORTS["desktop"])
    await page.add_init_script(
        "() => { try { window.localStorage.setItem('platform_theme', 'dark'); } catch (_) {} }"
    )
    for svc, url, shell in DARK_SPOT_CHECK:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.evaluate(
            "() => { document.documentElement.setAttribute('data-theme', 'dark');"
            " document.documentElement.removeAttribute('data-platform-theme-lock'); }"
        )
        await page.wait_for_timeout(2_500)
        await _shot(page, svc, url, shell, "dark")

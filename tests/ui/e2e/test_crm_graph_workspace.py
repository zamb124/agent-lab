"""E2E: единый graph workspace — редирект с /crm/mindmap."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_crm_mindmap_legacy_path_redirects_to_graph_workspace(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(f"{crm_ui.origin}/crm/mindmap", wait_until="domcontentloaded")
    await expect(ui_page_system).to_have_url(
        re.compile(r'/crm/graph\?.*view=mindmap'),
        timeout=60_000,
    )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_crm_mindmap_legacy_with_root_redirects(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/mindmap/entity_legacy_root_test",
        wait_until="domcontentloaded",
    )
    await expect(ui_page_system).to_have_url(
        re.compile(r'/crm/graph\?.*view=mindmap.*root=entity_legacy_root_test'),
        timeout=60_000,
    )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_crm_graph_workspace_switch_3d_to_mindmap_updates_url(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/graph?view=3d",
        wait_until="domcontentloaded",
    )
    await expect(ui_page_system.locator("crm-graph-workspace")).to_be_visible(timeout=60_000)
    toolbar = ui_page_system.locator("crm-graph-toolbar")
    await expect(toolbar).to_be_visible(timeout=30_000)
    await toolbar.get_by_role("button", name="Mind map", exact=True).click()
    await expect(ui_page_system).to_have_url(
        re.compile(r'/crm/graph\?.*view=mindmap'),
        timeout=60_000,
    )
    await expect(ui_page_system.locator("crm-mindmap-canvas")).to_be_visible(timeout=30_000)

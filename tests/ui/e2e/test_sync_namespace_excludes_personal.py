"""E2E: в Sync нет namespace switcher (personal/company — только API kind filter)."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import sync_e2e_open_with_namespace
from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_sync_namespace_picker_excludes_personal(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="nopersonal")
    await expect(
        ui_page_system.locator("sync-chat-list platform-sidebar-namespace-select")
    ).to_have_count(0)
    await expect(ui_page_system.locator("sync-chat-list")).to_be_visible(timeout=30_000)

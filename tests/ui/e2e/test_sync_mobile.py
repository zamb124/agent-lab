"""E2E: компактная шапка и меню на узком экране."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="mobile",
    doc_slug="mobile-sidebar-menu",
    title="Sync: мобильный список чатов",
    description=(
        "При ширине viewport как на телефоне Sync показывает список чатов прямо на главном экране, "
        "без дополнительного раскрытия сайдбара."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_mobile_opens_sidebar_from_header_menu(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await ui_page_system.set_viewport_size({"width": 390, "height": 844})

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await scenario.step("Sync на узком viewport", ui_page_system)

    mobile_list = ui_page_system.locator("sync-shell-page sync-chat-list")
    await expect(mobile_list).to_be_visible(timeout=30_000)
    await expect(
        mobile_list.locator("input.sync-chat-list-search-input")
    ).to_be_visible(timeout=30_000)
    await scenario.step("Список чатов доступен без лишнего клика", ui_page_system)

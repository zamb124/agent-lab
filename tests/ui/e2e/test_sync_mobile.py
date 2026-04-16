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
    title="Sync: мобильное меню и сайдбар",
    description=(
        "При ширине viewport как на телефоне отображается кнопка «Открыть меню»; "
        "по нажатию открывается боковая панель."
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

    menu_btn = ui_page_system.get_by_role("button", name="Открыть меню")
    await expect(menu_btn).to_be_visible(timeout=30_000)
    await menu_btn.click()

    await expect(ui_page_system.locator("platform-sidebar")).to_be_visible()
    await scenario.step("Сайдбар открыт с кнопки меню", ui_page_system)

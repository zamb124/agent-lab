"""E2E: личные сообщения (DM) с участником компании."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import sync_e2e_expect_ws_open
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="direct",
    doc_slug="open-dm-from-members",
    title="Sync: открытие чата с участником компании",
    description=(
        "В разделе «Личные» пользователь находит коллегу по имени и открывает с ним диалог."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_opens_direct_dm_from_member_list(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    peer_display = "System User 2"

    await ui_page_system.add_init_script("localStorage.removeItem('crm:last-namespace-by-company')")
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await sync_e2e_expect_ws_open(ui_page_system)
    await scenario.step("Sync открыт, раздел «Личные» доступен", ui_page_system)

    chat_list = ui_page_system.locator("sync-sidebar sync-chat-list").first
    await chat_list.locator(".search-scope-btn").nth(1).click()
    search = chat_list.locator("input.sync-chat-list-search-input")
    await expect(search).to_be_visible()
    await search.fill(peer_display)
    await scenario.step("Поиск по имени участника", ui_page_system)

    row = ui_page_system.locator("sync-direct-member-row").filter(
        has=ui_page_system.get_by_text(peer_display, exact=True)
    ).first
    await expect(row).to_be_visible(timeout=30_000)
    await row.click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()
    await scenario.step("Открыт чат с выбранным участником", ui_page_system)

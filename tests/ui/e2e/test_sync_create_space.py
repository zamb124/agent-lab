"""E2E: Sync без переключателя пространства — список всех чатов компании."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_expect_ws_open,
    sync_e2e_open_with_namespace,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="spaces",
    doc_slug="create-space",
    title="Sync: список чатов компании",
    description=(
        "Пользователь открывает Sync и видит список чатов по membership "
        "без переключателя пространства в сайдбаре."
    ),
    title_en="Sync: company chat list",
    description_en=(
        "The user opens Sync and sees the membership chat list "
        "without a namespace switcher in the sidebar."
    ),
    timeout_seconds=30,
)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_user_creates_space_with_name_and_description(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="select")
    await sync_e2e_expect_ws_open(ui_page_system)
    await expect(
        ui_page_system.locator("sync-chat-list platform-sidebar-namespace-select")
    ).to_have_count(0)
    await expect(
        ui_page_system.locator("sync-chat-list .header-action-btn").filter(
            has=ui_page_system.locator('platform-icon[name="settings"]')
        )
    ).to_be_visible(timeout=10_000)
    await scenario.step(
        "Открыт Sync без переключателя пространства",
        ui_page_system,
        label_en="Sync is open without a namespace switcher",
    )

    await expect(ui_page_system.locator("sync-chat-list")).to_be_visible()
    empty_or_list = ui_page_system.locator(
        "sync-chat-list .channel-item, sync-chat-list .empty, sync-channel-picker"
    )
    await expect(empty_or_list.first).to_be_visible(timeout=10_000)
    await scenario.step(
        "Список чатов компании доступен",
        ui_page_system,
        label_en="Company chat list is available",
    )

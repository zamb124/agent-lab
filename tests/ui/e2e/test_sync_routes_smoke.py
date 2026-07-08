"""E2E: smoke маршрутов /sync/settings и /sync/calls/scheduled."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_sync_settings_route_renders(
    sync_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await ui_page_system.goto(f"{sync_ui.origin}/sync/settings", wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await expect(ui_page_system.locator("sync-settings-page sync-chat-header .title")).to_have_text(
        re.compile(r"Sync settings|Настройки Sync"),
        timeout=30_000,
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_sync_calls_scheduled_route_renders(
    sync_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await ui_page_system.goto(f"{sync_ui.origin}/sync/calls/scheduled", wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await expect(ui_page_system.locator("sync-calls-scheduled-page sync-chat-header .title")).to_have_text(
        re.compile(r"Scheduled meetings|Запланированные встречи"),
        timeout=30_000,
    )
    create_meeting = ui_page_system.get_by_role("button", name="Создать встречу").or_(
        ui_page_system.get_by_role("button", name="New meeting")
    )
    await expect(create_meeting).to_be_visible()

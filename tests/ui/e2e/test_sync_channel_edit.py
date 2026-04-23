"""E2E: редактирование канала и модалка добавления участников."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_edits_channel_name_header_footer_and_opens_members_add(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал правок",
    )
    name_after_header = f"Канал после шапки {unique_id}"
    name_after_footer = f"Канал после футера {unique_id}"

    header = ui_page_system.locator("sync-chat-header")
    settings_btn = header.locator('button[title="Настройки"]').or_(header.locator('button[title="Settings"]'))
    await settings_btn.first.click()
    edit = ui_page_system.locator("sync-channel-edit-modal")
    await expect(edit).to_be_visible()
    await edit.locator("input.form-input").fill(name_after_header)
    await edit.locator("button.header-save-btn").click()
    await expect(edit).to_be_hidden(timeout=30_000)
    await expect(sync_sidebar_channel_nav(ui_page_system, name_after_header)).to_be_visible(timeout=30_000)

    await sync_sidebar_channel_nav(ui_page_system, name_after_header).click()
    await settings_btn.first.click()
    edit = ui_page_system.locator("sync-channel-edit-modal")
    await expect(edit).to_be_visible()
    await edit.locator("input.form-input").fill(name_after_footer)
    footer_save = edit.locator(".form-actions").get_by_role("button", name="Сохранить").or_(
        edit.locator(".form-actions").get_by_role("button", name="Save")
    )
    await footer_save.click()
    await expect(edit).to_be_hidden(timeout=30_000)
    await expect(sync_sidebar_channel_nav(ui_page_system, name_after_footer)).to_be_visible(timeout=30_000)

    await sync_sidebar_channel_nav(ui_page_system, name_after_footer).click()
    await settings_btn.first.click()
    edit = ui_page_system.locator("sync-channel-edit-modal")
    await expect(edit).to_be_visible()
    await edit.locator("button.add-members-icon-btn").click()
    members = ui_page_system.locator("sync-channel-members-add-modal")
    await expect(members).to_be_visible()
    members_title = members.get_by_role("heading", name="Добавить участников").or_(
        members.get_by_role("heading", name="Add members")
    )
    await expect(members_title).to_be_visible()

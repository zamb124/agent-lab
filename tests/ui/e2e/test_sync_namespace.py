"""E2E: селектор namespace в сайдбаре Sync не ломает список каналов."""

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
async def test_sync_namespace_select_keeps_channel_list_usable(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    channel_name = await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал NS",
    )

    ns_select = ui_page_system.locator("sync-sidebar select.ns-select")
    await expect(ns_select).to_be_visible()
    option_count = await ns_select.locator("option").count()
    if option_count > 1:
        value = await ns_select.locator("option").nth(1).get_attribute("value")
        if value is not None and value != "":
            await ns_select.select_option(value=value)

    await ns_select.select_option(index=0)
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=30_000
    )

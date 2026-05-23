"""E2E: пересылка сообщения в другой канал и закрепление (pin-strip)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_click_platform_button,
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_create_topic_channel_in_current_space,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI


async def _open_message_context_menu(page: Page, bubble) -> None:
    await bubble.click(button="right")
    await expect(page.locator("sync-message-context-menu")).to_have_attribute(
        "open", "", timeout=10_000
    )


async def _click_context_item(page: Page, *labels: str) -> None:
    pattern = re.compile("|".join(re.escape(label) for label in labels))
    item = page.locator("sync-message-context-menu").locator(".item").filter(has_text=pattern).first
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_user_forwards_message_to_second_channel(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="forward")

    channel_a = await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал A",
    )
    body = f"Текст пересылки {unique_id}"
    composer = ui_page_system.locator("sync-message-composer")
    await composer.locator('textarea[data-canon="composer"]').fill(body)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)

    channel_b = await sync_e2e_create_topic_channel_in_current_space(
        ui_page_system, unique_id, channel_prefix="Канал B"
    )

    await sync_sidebar_channel_nav(ui_page_system, channel_a).click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()
    bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=body)
    await _open_message_context_menu(ui_page_system, bubble)
    await _click_context_item(ui_page_system, "Переслать", "Forward")

    fwd = ui_page_system.locator("sync-forward-modal")
    await expect(fwd).to_be_visible()
    await expect(fwd.locator(".modal-title")).to_contain_text(
        re.compile(r"Куда переслать|Forward to")
    )
    await fwd.locator(".form-item").filter(has_text=channel_b).first.click()
    await sync_e2e_click_platform_button(fwd.locator(".form-actions"), "Переслать", "Forward")
    await expect(fwd).to_be_hidden(timeout=30_000)

    await sync_sidebar_channel_nav(ui_page_system, channel_b).click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_pins_message_shows_pin_strip(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="pin")

    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал закрепов",
    )
    body = f"Закрепляемое {unique_id}"
    composer = ui_page_system.locator("sync-message-composer")
    await composer.locator('textarea[data-canon="composer"]').fill(body)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)

    bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=body)
    await _open_message_context_menu(ui_page_system, bubble)
    await _click_context_item(ui_page_system, "Закрепить", "Pin")

    pin_strip = ui_page_system.locator("sync-pin-strip")
    await expect(pin_strip).to_be_visible(timeout=30_000)
    await expect(pin_strip.locator(".preview")).to_contain_text(body, timeout=15_000)

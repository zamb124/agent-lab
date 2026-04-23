"""E2E: пересылка сообщения в другой канал и закрепление (pin-strip)."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_create_topic_channel_in_current_space,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_user_forwards_message_to_second_channel(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    channel_a = await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал A",
    )
    body = f"Текст пересылки {unique_id}"
    composer = ui_page_system.locator("message-composer")
    await composer.locator("textarea[placeholder='Сообщение...']").fill(body)
    await composer.locator('button.send[title="Отправить"]').click()
    await expect(
        ui_page_system.locator("message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)

    channel_b = await sync_e2e_create_topic_channel_in_current_space(
        ui_page_system, unique_id, channel_prefix="Канал B"
    )

    await sync_sidebar_channel_nav(ui_page_system, channel_a).click()
    await expect(ui_page_system.locator("chat-view")).to_be_visible()
    bubble = ui_page_system.locator("message-bubble").filter(has_text=body)
    await bubble.click(button="right")
    fwd_menu = ui_page_system.get_by_role("button", name="Переслать").or_(
        ui_page_system.get_by_role("button", name="Forward")
    )
    await fwd_menu.click()

    fwd = ui_page_system.locator("sync-forward-modal")
    await expect(fwd).to_be_visible()
    fwd_title = fwd.get_by_role("heading", name="Куда переслать").or_(fwd.get_by_role("heading", name="Forward to"))
    await expect(fwd_title).to_be_visible()
    await fwd.locator(".form-item").filter(has_text=channel_b).first.click()
    fwd_submit = fwd.locator(".form-actions").get_by_role("button", name="Переслать").or_(
        fwd.locator(".form-actions").get_by_role("button", name="Forward")
    )
    await fwd_submit.click()
    await expect(fwd).to_be_hidden(timeout=30_000)

    await sync_sidebar_channel_nav(ui_page_system, channel_b).click()
    await expect(
        ui_page_system.locator("message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_pins_message_shows_pin_strip(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал закрепов",
    )
    body = f"Закрепляемое {unique_id}"
    composer = ui_page_system.locator("message-composer")
    await composer.locator("textarea[placeholder='Сообщение...']").fill(body)
    await composer.locator('button.send[title="Отправить"]').click()
    await expect(
        ui_page_system.locator("message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)

    bubble = ui_page_system.locator("message-bubble").filter(has_text=body)
    await bubble.click(button="right")
    pin_btn = ui_page_system.get_by_role("button", name="Закрепить").or_(
        ui_page_system.get_by_role("button", name="Pin")
    )
    await pin_btn.click()

    pin_strip = ui_page_system.locator("sync-pin-strip")
    await expect(pin_strip).to_be_visible(timeout=30_000)
    await expect(pin_strip.locator(".preview")).to_contain_text(body, timeout=15_000)

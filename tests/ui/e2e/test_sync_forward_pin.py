"""E2E: пересылка сообщения в другой канал и закрепление (pin-strip)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_channel_id_by_name,
    sync_api_post_plain_message,
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
@pytest.mark.timeout(60)
async def test_user_forwards_message_to_second_channel(
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="forward")

    channel_a = await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал A",
    )
    body = f"Текст пересылки {unique_id}"
    channel_a_id = await sync_api_channel_id_by_name(
        sync_ui.origin, auth_token_system, channel_a
    )
    await sync_api_post_plain_message(
        sync_ui.origin, auth_token_system, channel_a_id, body
    )
    await ui_page_system.evaluate(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.dispatch !== 'function') {
                throw new Error('__PLATFORM_BUS__ недоступен для reload messages');
            }
            bus.dispatch('sync/channels/list_requested', null);
        }"""
    )
    await sync_sidebar_channel_nav(ui_page_system, channel_a).click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=15_000)
    # Ждём confirmed message_id — иначе forward уходит с local_* и не попадает в канал B.
    await ui_page_system.wait_for_function(
        """(text) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            const channelId = state.syncChannels && state.syncChannels.selectedChannelId;
            const store = state.syncMessagesStore;
            const data = store && store.byChannelId && channelId
                ? store.byChannelId[channelId]
                : null;
            if (!data || !Array.isArray(data.items)) return false;
            return data.items.some((m) => {
                if (!m || typeof m.message_id !== 'string' || m.message_id.startsWith('local_')) {
                    return false;
                }
                const contents = Array.isArray(m.contents) ? m.contents : [];
                return contents.some((c) => c && c.data && c.data.body === text);
            });
        }""",
        arg=body,
        timeout=15_000,
    )

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
    await ui_page_system.evaluate(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.dispatch !== 'function' || typeof bus.getState !== 'function') {
                throw new Error('__PLATFORM_BUS__ недоступен для reload messages');
            }
            const channelId = bus.getState().syncChannels?.selectedChannelId;
            if (typeof channelId !== 'string' || !channelId) {
                throw new Error('selectedChannelId отсутствует после открытия канала B');
            }
            bus.dispatch('sync/messages/list_requested', { channel_id: channelId });
        }"""
    )
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
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
    await composer.locator("button.send").evaluate("(el) => el.click()")
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(body, exact=True)
    ).to_be_visible(timeout=10_000)

    # Ждём confirmed message_id (не optimistic local_*), иначе pin → «Сообщение не найдено».
    await ui_page_system.wait_for_function(
        """(text) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            const channelId = state.syncChannels && state.syncChannels.selectedChannelId;
            const store = state.syncMessagesStore;
            const data = store && store.byChannelId && channelId
                ? store.byChannelId[channelId]
                : null;
            if (!data || !Array.isArray(data.items)) return false;
            return data.items.some((m) => {
                if (!m || typeof m.message_id !== 'string' || m.message_id.startsWith('local_')) {
                    return false;
                }
                const contents = Array.isArray(m.contents) ? m.contents : [];
                return contents.some((c) => c && c.data && c.data.body === text);
            });
        }""",
        arg=body,
        timeout=10_000,
    )
    bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=body)
    await _open_message_context_menu(ui_page_system, bubble)
    await _click_context_item(ui_page_system, "Закрепить", "Pin")

    pin_strip = ui_page_system.locator("sync-pin-strip")
    await expect(pin_strip.locator(".row")).to_be_visible(timeout=10_000)
    await expect(pin_strip.locator(".preview")).to_contain_text(body, timeout=5_000)

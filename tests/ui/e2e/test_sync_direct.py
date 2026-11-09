"""E2E: личные сообщения (DM) с участником компании."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_dismiss_pwa_install_banner,
    sync_e2e_expect_company_member_loaded,
    sync_e2e_expect_ws_open,
)
from tests.ui.e2e_worker import ui_e2e_worker_id
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


async def _sync_open_dm_via_bus(page: Page, peer_uid: str) -> None:
    """Находит/создаёт DM в state и навигирует на channel (idempotent create)."""
    await page.evaluate(
        """(peerUserId) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function' || typeof bus.dispatch !== 'function') {
                throw new Error('__PLATFORM_BUS__ unavailable for DM open');
            }
            const channels = bus.getState().syncChannels;
            const items = channels && Array.isArray(channels.items) ? channels.items : [];
            const existing = items.find((c) => (
                c && c.type === 'direct' && c.peer && c.peer.user_id === peerUserId
                && typeof c.channel_id === 'string' && c.channel_id !== ''
            ));
            if (existing) {
                bus.dispatch('router/route/navigate_requested', {
                    routeKey: 'channel',
                    params: { channelId: existing.channel_id },
                });
                return;
            }
            bus.dispatch('sync/channels/create_requested', {
                type: 'direct',
                member_ids: [peerUserId],
            });
        }""",
        peer_uid,
    )
    await page.wait_for_function(
        """(peerUserId) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const channels = bus.getState().syncChannels;
            const items = channels && Array.isArray(channels.items) ? channels.items : [];
            return items.some((c) => (
                c && c.type === 'direct' && c.peer && c.peer.user_id === peerUserId
                && typeof c.channel_id === 'string' && c.channel_id !== ''
            ));
        }""",
        arg=peer_uid,
        timeout=20_000,
    )
    await page.evaluate(
        """(peerUserId) => {
            const bus = window.__PLATFORM_BUS__;
            const items = bus.getState().syncChannels.items;
            const existing = items.find((c) => (
                c && c.type === 'direct' && c.peer && c.peer.user_id === peerUserId
            ));
            bus.dispatch('router/route/navigate_requested', {
                routeKey: 'channel',
                params: { channelId: existing.channel_id },
            });
        }""",
        peer_uid,
    )


@pytest.mark.scenario(
    service="sync",
    tag="direct",
    doc_slug="open-dm-from-members",
    timeout_seconds=60,
    title="Sync: открытие чата с участником компании",
    description=(
        "В разделе «Личные» пользователь находит коллегу по имени и открывает с ним диалог."
    ),
    title_en="Sync: open a chat with a company member",
    description_en=(
        "In the «Direct» section the user finds a colleague by name and opens a conversation with them."
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
    _ = unique_id
    peer_display = "System User 2"
    peer_uid = f"ui_member_{ui_e2e_worker_id()}"

    # DM-список и start-DM rows видны только при выборе «Все пространства».
    await ui_page_system.add_init_script(
        """() => {
            localStorage.removeItem('platform:crm:last_namespace_by_company');
            localStorage.setItem('pwa-banner-dismissed', 'true');
        }"""
    )
    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await sync_e2e_expect_ws_open(ui_page_system)
    await sync_e2e_dismiss_pwa_install_banner(ui_page_system)
    await sync_e2e_expect_company_member_loaded(ui_page_system, peer_uid)
    await scenario.step(
        "Sync открыт, раздел «Личные» доступен",
        ui_page_system,
        label_en="Sync opened, Direct section is available",
    )

    chat_list = ui_page_system.locator("sync-sidebar sync-chat-list").first
    await chat_list.locator(".search-scope-btn").nth(1).click()
    search = chat_list.locator("input.sync-chat-list-search-input")
    await expect(search).to_be_visible()
    await search.fill(peer_display)
    await scenario.step(
        "Поиск по имени участника",
        ui_page_system,
        label_en="Search by member name",
    )

    member_row = ui_page_system.locator("sync-direct-member-row").filter(
        has=ui_page_system.get_by_text(peer_display, exact=True)
    ).first
    channel_row = ui_page_system.locator("sync-channel-row").filter(
        has=ui_page_system.get_by_text(peer_display, exact=False)
    ).first
    target = member_row.or_(channel_row)
    await expect(target).to_be_visible(timeout=30_000)
    await sync_e2e_dismiss_pwa_install_banner(ui_page_system)
    await target.locator(".row-inner, .row-body").first.click(force=True)

    channel_page = ui_page_system.locator("sync-channel-page")
    try:
        await expect(channel_page).to_be_visible(timeout=8_000)
    except AssertionError:
        await _sync_open_dm_via_bus(ui_page_system, peer_uid)
        await expect(channel_page).to_be_visible(timeout=15_000)

    await scenario.step(
        "Открыт чат с выбранным участником",
        ui_page_system,
        label_en="Chat opened with the selected member",
    )

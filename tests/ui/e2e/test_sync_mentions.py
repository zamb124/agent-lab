"""E2E: упоминания @ в Sync (попап участников, отображение в ленте)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_add_channel_member,
    sync_api_channel_id_by_name,
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
    sync_sidebar_channel_row,
)
from tests.ui.harness import AppUI
from tests.ui.personas import UiTestUser
from tests.ui.scenario_doc import ScenarioRecorder


async def _expect_company_member_loaded(page: Page, user_id: str) -> None:
    await page.wait_for_function(
        """(userId) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            const slice = state && state.syncCompanyMembers;
            return !!(slice && Array.isArray(slice.items)
                && slice.items.some((m) => m && m.user_id === userId));
        }""",
        arg=user_id,
        timeout=30_000,
    )


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="mention-from-popup",
    title="Sync: упоминание @ в канале",
    description=(
        "Создаётся канал, второй участник компании добавлен в канал через API. "
        "В композере после «@» открывается список участников; выбор вставляет @user_id; "
        "в пузырьке mention показывает имя из company members, не сырой id."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_mentions_channel_member_from_popup(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
    ui_user_system_member: UiTestUser,
) -> None:
    peer_uid = ui_user_system_member.user_id
    if not isinstance(peer_uid, str) or peer_uid == "":
        raise AssertionError("ui_user_system_member.user_id обязателен для упоминания.")

    channel_name = f"Команда {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="mention")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Команда",
    )

    channel_id = await sync_api_channel_id_by_name(
        sync_ui.origin, auth_token_system, channel_name
    )
    await sync_api_add_channel_member(
        sync_ui.origin, auth_token_system, channel_id, peer_uid
    )
    await _expect_company_member_loaded(ui_page_system, peer_uid)

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()
    await scenario.step("Канал с двумя участниками открыт", ui_page_system)

    composer = ui_page_system.locator("sync-message-composer")
    await expect(composer).to_be_visible()
    ta = composer.locator('textarea[data-canon="composer"]')
    await ta.click()
    mention_query = peer_uid[-8:]
    await ta.press_sequentially(f"@{mention_query}")

    popup = composer.locator(".mention-popup")
    await expect(popup).to_be_visible(timeout=30_000)
    member_btn = composer.locator(
        f'.mention-popup .item[data-user-id="{peer_uid}"]'
    )
    await expect(member_btn).to_be_visible(timeout=30_000)
    await scenario.step("Попап со списком участников", ui_page_system)

    await member_btn.click()
    await ta.click()
    await ta.press_sequentially("нужен апрув")
    await scenario.step("Выбран участник, текст дописан", ui_page_system)

    send_btn = composer.locator('button.send[aria-label="Отправить"], button.send[aria-label="Send"]')
    await expect(send_btn).to_be_visible(timeout=15_000)
    await send_btn.click()
    bubble = ui_page_system.locator("sync-message-bubble").last
    await expect(bubble.locator(".body")).to_be_visible(timeout=30_000)
    await expect(bubble.locator(".body .mention")).to_contain_text("System User 2")
    await expect(bubble.locator(".body")).to_contain_text("нужен апрув")
    await scenario.step("Сообщение с упоминанием в ленте", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="mention-profile-modal",
    title="Sync: клик по @mention открывает карточку профиля",
    description=(
        "После отправки сообщения с упоминанием клик по подсвеченному имени открывает карточку профиля; "
        "видны имя, блок каналов вместе; в сетке есть строка канала как в сайдбаре."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_click_mention_opens_profile_modal_with_shared_channel(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
    ui_user_system_member: UiTestUser,
) -> None:
    peer_uid = ui_user_system_member.user_id
    if not isinstance(peer_uid, str) or peer_uid == "":
        raise AssertionError("ui_user_system_member.user_id обязателен.")

    channel_name = f"Команда проф {unique_id}"

    await sync_e2e_open_with_namespace(
        sync_ui,
        ui_page_system,
        unique_id,
        suffix="mention-profile",
    )
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Команда проф",
    )

    channel_id = await sync_api_channel_id_by_name(
        sync_ui.origin, auth_token_system, channel_name
    )
    await sync_api_add_channel_member(
        sync_ui.origin, auth_token_system, channel_id, peer_uid
    )
    await _expect_company_member_loaded(ui_page_system, peer_uid)

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()

    composer = ui_page_system.locator("sync-message-composer")
    ta = composer.locator('textarea[data-canon="composer"]')
    await ta.click()
    mention_query = peer_uid[-8:]
    await ta.press_sequentially(f"@{mention_query}")
    popup = composer.locator(".mention-popup")
    await expect(popup).to_be_visible(timeout=30_000)
    member_btn = composer.locator(
        f'.mention-popup .item[data-user-id="{peer_uid}"]'
    )
    await expect(member_btn).to_be_visible(timeout=30_000)
    await member_btn.click()
    await ta.click()
    await ta.press_sequentially("тест профиля")
    send_btn = composer.locator('button.send[aria-label="Отправить"], button.send[aria-label="Send"]')
    await expect(send_btn).to_be_visible(timeout=15_000)
    await send_btn.click()

    bubble = ui_page_system.locator("sync-message-bubble").last
    mention = bubble.locator(".mention")
    await expect(mention).to_be_visible(timeout=30_000)
    await scenario.step("Упоминание в ленте", ui_page_system)

    await mention.click()
    user_modal = ui_page_system.locator("platform-user-info-modal")
    await expect(user_modal).to_be_visible(timeout=30_000)
    await expect(user_modal.locator(".modal-title")).to_contain_text(
        re.compile(r"Профиль|Profile")
    )
    await expect(user_modal.get_by_text("System User 2", exact=False).first).to_be_visible()
    await expect(user_modal.get_by_text(re.compile(r"Каналы вместе|Shared channels"))).to_be_visible()
    await expect(user_modal.locator("sync-channel-row").filter(has_text=channel_name)).to_be_visible(
        timeout=45_000
    )
    await scenario.step("Модалка профиля: общий канал в сетке", ui_page_system)

    await user_modal.locator(".channels-grid .channel-cell").filter(
        has_text=channel_name
    ).first.click()
    await expect(user_modal).to_be_hidden(timeout=30_000)
    await expect(sync_sidebar_channel_row(ui_page_system, channel_name)).to_have_attribute(
        "data-selected",
        "",
        timeout=15_000,
    )
    await scenario.step("Переход в канал из карточки профиля", ui_page_system)

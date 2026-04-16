"""E2E: упоминания @ в Sync (попап участников, отображение в ленте)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_add_channel_member,
    sync_api_channel_id_by_name,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI
from tests.ui.personas import UiTestUser
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="mention-from-popup",
    title="Sync: упоминание @ в канале",
    description=(
        "Создаётся канал, второй участник компании добавлен в канал через API. "
        "В композере после «@» открывается список участников; выбор вставляет @user_id; "
        "в пузырьке .msg-mention показывает имя из company members, не сырой id."
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

    space_name = f"E2E @ space {unique_id}"
    channel_name = f"Команда {unique_id}"

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    await ui_page_system.get_by_role("button", name="Создать пространство").click()
    sm = ui_page_system.locator("space-settings-modal")
    await expect(sm).to_be_visible()
    ins = sm.locator('input.input:not([type="file"])')
    await ins.nth(0).fill(space_name)
    await sm.get_by_role("button", name="Создать", exact=True).click()
    await expect(ui_page_system.get_by_role("button", name=space_name)).to_be_visible(
        timeout=30_000
    )

    await ui_page_system.get_by_role("button", name="Создать канал").click()
    ch_modal = ui_page_system.locator("channel-settings-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.get_by_placeholder("Название канала").fill(channel_name)
    await ch_modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=30_000
    )

    channel_id = await sync_api_channel_id_by_name(
        sync_ui.origin, auth_token_system, channel_name
    )
    await sync_api_add_channel_member(
        sync_ui.origin, auth_token_system, channel_id, peer_uid
    )

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("chat-view")).to_be_visible()
    await scenario.step("Канал с двумя участниками открыт", ui_page_system)

    composer = ui_page_system.locator("message-composer")
    await expect(composer).to_be_visible()
    ta = composer.locator("textarea[placeholder='Сообщение...']")
    await ta.click()
    await ta.press("@")

    popup = composer.locator(".mention-popup")
    await expect(popup).to_be_visible(timeout=30_000)
    member_btn = composer.locator("button.mention-item").filter(
        has_text="System User 2"
    ).first
    await expect(member_btn).to_be_visible(timeout=30_000)
    await scenario.step("Попап со списком участников", ui_page_system)

    await member_btn.click()
    await ta.press_sequentially("нужен апрув")
    await scenario.step("Выбран участник, текст дописан", ui_page_system)

    await composer.locator('button.send[title="Отправить"]').click()
    bubble = ui_page_system.locator("message-bubble").last
    await expect(bubble.locator(".msg-text")).to_be_visible(timeout=30_000)
    await expect(bubble.locator(".msg-text .msg-mention")).to_contain_text("System User 2")
    await expect(bubble.locator(".msg-text")).to_contain_text("нужен апрув")
    await scenario.step("Сообщение с упоминанием в ленте", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="mention-profile-modal",
    title="Sync: клик по @mention открывает карточку профиля",
    description=(
        "После отправки сообщения с упоминанием клик по подсвеченному имени открывает user-info-modal; "
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

    space_name = f"E2E prof mention space {unique_id}"
    channel_name = f"Команда проф {unique_id}"

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    await ui_page_system.get_by_role("button", name="Создать пространство").click()
    sm = ui_page_system.locator("space-settings-modal")
    await expect(sm).to_be_visible()
    ins = sm.locator('input.input:not([type="file"])')
    await ins.nth(0).fill(space_name)
    await sm.get_by_role("button", name="Создать", exact=True).click()
    await expect(ui_page_system.get_by_role("button", name=space_name)).to_be_visible(
        timeout=30_000
    )

    await ui_page_system.get_by_role("button", name="Создать канал").click()
    ch_modal = ui_page_system.locator("channel-settings-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.get_by_placeholder("Название канала").fill(channel_name)
    await ch_modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=30_000
    )

    channel_id = await sync_api_channel_id_by_name(
        sync_ui.origin, auth_token_system, channel_name
    )
    await sync_api_add_channel_member(
        sync_ui.origin, auth_token_system, channel_id, peer_uid
    )

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("chat-view")).to_be_visible()

    composer = ui_page_system.locator("message-composer")
    ta = composer.locator("textarea[placeholder='Сообщение...']")
    await ta.click()
    await ta.press("@")
    popup = composer.locator(".mention-popup")
    await expect(popup).to_be_visible(timeout=30_000)
    await composer.locator("button.mention-item").filter(has_text="System User 2").first.click()
    await ta.press_sequentially("тест профиля")
    await composer.locator('button.send[title="Отправить"]').click()

    bubble = ui_page_system.locator("message-bubble").last
    mention = bubble.locator(".msg-mention--interactive")
    await expect(mention).to_be_visible(timeout=30_000)
    await scenario.step("Упоминание в ленте", ui_page_system)

    await mention.click()
    user_modal = ui_page_system.locator("user-info-modal")
    await expect(user_modal).to_be_visible(timeout=30_000)
    await expect(user_modal.get_by_role("heading", name="Профиль")).to_be_visible()
    await expect(user_modal.get_by_text("System User 2", exact=False).first).to_be_visible()
    await expect(user_modal.get_by_text("Каналы вместе")).to_be_visible()
    await expect(user_modal.locator("sync-channel-row").filter(has_text=channel_name)).to_be_visible(
        timeout=45_000
    )
    await scenario.step("Модалка профиля: общий канал в сетке", ui_page_system)

    await user_modal.locator(".channels-grid .channel-cell").filter(
        has_text=channel_name
    ).first.click()
    await expect(user_modal).to_be_hidden(timeout=30_000)
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_have_class(
        re.compile(r"\bactive\b"),
        timeout=15_000,
    )
    await scenario.step("Переход в канал из карточки профиля", ui_page_system)

"""E2E: настройки канала (мьют) и просмотр профиля из чужого сообщения."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_add_channel_member,
    sync_api_channel_id_by_name,
    sync_api_post_plain_message,
    sync_e2e_click_platform_button,
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_expect_ws_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
    sync_sidebar_channel_settings_gear,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="settings",
    doc_slug="mute-channel-notifications",
    title="Sync: мьют уведомлений в настройках канала",
    description=(
        "Пользователь открывает настройки topic-канала и включает «Не беспокоить»."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_mutes_channel_notifications(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    channel_name = f"Канал настроек {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="mute")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал настроек",
    )

    await sync_sidebar_channel_settings_gear(ui_page_system, channel_name).click()
    settings_modal = ui_page_system.locator("sync-channel-edit-modal")
    await expect(settings_modal).to_be_visible()
    await expect(settings_modal.locator(".modal-title")).to_contain_text(
        re.compile(r"Настройки канала|Channel settings")
    )
    await scenario.step("Открыты настройки канала", ui_page_system)

    mute_switch = settings_modal.locator(".toggle-row").filter(
        has_text=re.compile(r"Не беспокоить|Do not disturb")
    ).locator("platform-switch")
    await mute_switch.click()
    await expect(mute_switch).to_have_attribute("checked", "", timeout=15_000)
    await scenario.step("Включён мьют уведомлений", ui_page_system)

    await sync_e2e_click_platform_button(settings_modal, "Сохранить", "Save")
    await expect(settings_modal).to_be_hidden()


@pytest.mark.scenario(
    service="sync",
    tag="settings",
    doc_slug="peer-profile-from-message",
    title="Sync: профиль отправителя из сообщения",
    description=(
        "В канал добавлен участник; его сообщение создаётся через API; владелец открывает профиль "
        "по кнопке на аватаре в пузырьке чужого сообщения."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_owner_opens_peer_profile_from_message_bubble(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    auth_token_system_user2: str,
    system_user2_id: str,
    unique_id: str,
) -> None:
    channel_name = f"Канал профиля {unique_id}"
    msg_text = f"Сообщение от участника {unique_id}"
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="profile")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал профиля",
    )

    channel_id = await sync_api_channel_id_by_name(sync_ui.origin, auth_token_system, channel_name)
    await sync_api_add_channel_member(
        sync_ui.origin,
        auth_token_system,
        channel_id,
        system_user2_id,
    )
    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await sync_e2e_expect_ws_open(ui_page_system)
    await scenario.step("В канал добавлен второй участник", ui_page_system)

    await sync_api_post_plain_message(
        sync_ui.origin,
        auth_token_system_user2,
        channel_id,
        msg_text,
    )
    await scenario.step("Сообщение от второго участника отправлено через API", ui_page_system)

    await ui_page_system.reload(wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await sync_e2e_expect_ws_open(ui_page_system)
    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(msg_text, exact=True)
    ).to_be_visible(timeout=45_000)
    peer_bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=msg_text)
    await peer_bubble.locator(".sender").click()
    user_modal = ui_page_system.locator("platform-user-info-modal")
    await expect(user_modal).to_be_visible()
    await expect(user_modal.locator(".modal-title")).to_contain_text(
        re.compile(r"Профиль|Profile")
    )
    await expect(user_modal.get_by_text("System User 2", exact=False)).to_be_visible()
    await expect(user_modal.get_by_text(re.compile(r"Каналы вместе|Shared channels"))).to_be_visible()
    await scenario.step("Открыта модалка профиля отправителя", ui_page_system)

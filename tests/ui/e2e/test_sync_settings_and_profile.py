"""E2E: настройки канала (мьют) и просмотр профиля из чужого сообщения."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_channel_id_by_name,
    sync_api_post_plain_message,
    sync_sidebar_channel_nav,
    sync_sidebar_channel_settings_gear,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

@pytest.mark.scenario(
    service="sync",
    tag="settings",
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
    space_name = f"E2E mute space {unique_id}"
    channel_name = f"Канал настроек {unique_id}"

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

    await sync_sidebar_channel_settings_gear(ui_page_system, channel_name).click()
    settings_modal = ui_page_system.locator("channel-settings-modal")
    await expect(settings_modal).to_be_visible()
    await expect(ui_page_system.get_by_role("heading", name="Настройки канала")).to_be_visible()
    await scenario.step("Открыты настройки канала", ui_page_system)

    checkbox = settings_modal.locator(
        'label:has-text("Не беспокоить (без уведомлений о новых сообщениях)")'
    ).locator('input[type="checkbox"]')
    await checkbox.check()
    await expect(checkbox).to_be_checked()
    await scenario.step("Включён мьют уведомлений", ui_page_system)

    await settings_modal.get_by_role("button", name="Отмена").click()
    await expect(settings_modal).to_be_hidden()


@pytest.mark.scenario(
    service="sync",
    tag="settings",
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
    space_name = f"E2E prof space {unique_id}"
    channel_name = f"Канал профиля {unique_id}"
    msg_text = f"Сообщение от участника {unique_id}"
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

    await sync_sidebar_channel_settings_gear(ui_page_system, channel_name).click()
    settings_modal = ui_page_system.locator("channel-settings-modal")
    await expect(settings_modal).to_be_visible()
    await settings_modal.get_by_role("button", name="Добавить участников").click()
    pick_row = settings_modal.locator("label.pick-row").filter(has_text=system_user2_id).first
    await expect(pick_row).to_be_visible(timeout=30_000)
    await pick_row.locator('input[type="checkbox"]').check()
    await settings_modal.get_by_role("button", name="Добавить выбранных (1)").click()
    await expect(settings_modal.get_by_text(system_user2_id, exact=False).first).to_be_visible(
        timeout=30_000
    )
    await settings_modal.get_by_role("button", name="Отмена").click()
    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator(".ws-badge.open")).to_be_visible(timeout=30_000)
    await scenario.step("В канал добавлен второй участник", ui_page_system)

    channel_id = await sync_api_channel_id_by_name(sync_ui.origin, auth_token_system, channel_name)
    await sync_api_post_plain_message(
        sync_ui.origin,
        auth_token_system_user2,
        channel_id,
        msg_text,
    )
    await scenario.step("Сообщение от второго участника отправлено через API", ui_page_system)

    await ui_page_system.reload(wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await expect(ui_page_system.locator(".ws-badge.open")).to_be_visible(timeout=30_000)
    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(
        ui_page_system.locator("message-bubble").get_by_text(msg_text, exact=True)
    ).to_be_visible(timeout=45_000)
    peer_bubble = ui_page_system.locator("message-bubble").filter(has_text=msg_text)
    await peer_bubble.get_by_role("button", name=re.compile(r"^Профиль:\s+")).click()
    user_modal = ui_page_system.locator("user-info-modal")
    await expect(user_modal).to_be_visible()
    await expect(user_modal.get_by_role("heading", name="Профиль")).to_be_visible()
    await expect(user_modal.get_by_text("System User 2", exact=False)).to_be_visible()
    await expect(user_modal.get_by_text("Каналы вместе")).to_be_visible()
    await scenario.step("Открыта модалка профиля отправителя", ui_page_system)

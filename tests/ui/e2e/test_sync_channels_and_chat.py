"""E2E: канал в пространстве и отправка сообщения."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import sync_sidebar_channel_nav
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="channels",
    doc_slug="create-topic-channel",
    title="Sync: создание канала в пространстве",
    description=(
        "После создания пространства пользователь создаёт topic-канал через «+» у раздела «Каналы» "
        "и подтверждает создание."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_creates_topic_channel(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    space_name = f"E2E ch space {unique_id}"
    channel_name = f"Канал {unique_id}"

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
    await scenario.step("Пространство создано", ui_page_system)

    await ui_page_system.get_by_role("button", name="Создать канал").click()
    ch_modal = ui_page_system.locator("channel-settings-modal")
    await expect(ch_modal).to_be_visible()
    await expect(ui_page_system.get_by_role("heading", name="Создать канал")).to_be_visible()
    await scenario.step("Открыто создание канала", ui_page_system)

    await ch_modal.get_by_placeholder("Название канала").fill(channel_name)
    await scenario.step("Введено название канала", ui_page_system)

    await ch_modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=30_000
    )
    await scenario.step("Канал появился в сайдбаре", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="send-message-in-channel",
    title="Sync: отправка сообщения в канал",
    description=(
        "Пользователь открывает канал, вводит текст в поле «Сообщение…» и отправляет его; "
        "текст отображается в ленте."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_sends_message_in_channel(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    space_name = f"E2E msg space {unique_id}"
    channel_name = f"Общий {unique_id}"
    message_text = f"Привет из E2E {unique_id}"

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

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("chat-view")).to_be_visible()
    await scenario.step("Выбран канал, открыт чат", ui_page_system)

    composer = ui_page_system.locator("message-composer")
    await expect(composer).to_be_visible()
    await composer.locator("textarea[placeholder='Сообщение...']").fill(message_text)
    await composer.locator('button.send[title="Отправить"]').click()
    await expect(
        ui_page_system.locator("message-bubble").get_by_text(message_text, exact=True)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Сообщение отображается в ленте", ui_page_system)

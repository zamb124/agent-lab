"""E2E: канал в пространстве и отправка сообщения."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_click_create_channel,
    sync_e2e_click_platform_button,
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
)
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
    channel_name = f"Канал {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="ch")
    await scenario.step("Выбрано пространство Sync", ui_page_system)

    await sync_e2e_click_create_channel(ui_page_system)
    ch_modal = ui_page_system.locator("sync-channel-create-modal")
    await expect(ch_modal).to_be_visible()
    await scenario.step("Открыто создание канала", ui_page_system)

    await ch_modal.locator("input.field-pill-input").first.fill(channel_name)
    await scenario.step("Введено название канала", ui_page_system)

    await sync_e2e_click_platform_button(ch_modal, "Создать", "Create")
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
    message_text = f"Привет из E2E {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="msg")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Общий",
    )

    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()
    await scenario.step("Выбран канал, открыт чат", ui_page_system)

    composer = ui_page_system.locator("sync-message-composer")
    await expect(composer).to_be_visible()
    await composer.locator('textarea[data-canon="composer"]').fill(message_text)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(message_text, exact=True)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Сообщение отображается в ленте", ui_page_system)

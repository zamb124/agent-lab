"""E2E: звонок в канале и страница входа по ссылке."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


async def _click_channel_call_button(page: Page) -> None:
    call_button = page.locator("sync-chat-header button.icon-btn.accent").first
    await expect(call_button).to_be_visible(timeout=30_000)
    await call_button.click()


async def _ensure_overlay_chat_open(overlay) -> None:
    chat_input = overlay.locator("textarea.chat-input")
    if await chat_input.is_visible(timeout=1_000):
        return
    toggle = overlay.locator(
        'button.ctrl[title="Показать чат"], button.ctrl[title="Show chat"]'
    ).first
    await expect(toggle).to_be_visible(timeout=30_000)
    await toggle.click()
    await expect(chat_input).to_be_visible(timeout=30_000)


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="channel-call-overlay",
    title="Sync: старт звонка из шапки канала",
    description=(
        "В topic-канале пользователь нажимает «Звонок в этом канале»; после ответа сервера "
        "отображается оверлей звонка (атрибут data-call-active на sync-app)."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_starts_channel_call_overlay(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="call")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал звонка",
    )
    await scenario.step("Открыт topic-канал", ui_page_system)

    await _click_channel_call_button(ui_page_system)
    await expect(ui_page_system.locator("sync-app")).to_have_attribute("data-call-active", "", timeout=90_000)
    await expect(ui_page_system.locator("sync-call-overlay-modal")).to_be_visible(timeout=15_000)
    await scenario.step("Отображается оверлей звонка", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="join-invalid-token",
    title="Sync: страница входа по недействительной ссылке",
    description="Публичная страница /sync/join/{token} показывает сообщение об ошибке для несуществующего токена.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_call_join_page_shows_error_for_invalid_token(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    page: Page,
) -> None:
    await page.goto(f"{sync_ui.origin}/sync/join/invalid-token-e2e", wait_until="domcontentloaded")
    await expect(page.locator("sync-call-join-page .error-text")).to_contain_text(
        re.compile(
            r"Ссылка не найдена или истекла|Не удалось загрузить информацию о звонке|"
            r"Link not found or expired|Could not load call information"
        ),
        timeout=30_000,
    )
    await scenario.step("Сообщение об ошибке для неверной ссылки", page)


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="call-overlay-chat-sync",
    title="Sync: чат в оверлее звонка синхронизирован с каналом",
    description=(
        "Сообщение из основного чата видно в call-overlay, а сообщение из call-overlay после завершения звонка "
        "отображается в ленте канала."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_call_overlay_channel_chat_syncs_with_main_chat(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    main_text = f"Сообщение до звонка {unique_id}"
    overlay_text = f"Сообщение из оверлея {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="overlay")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал чата звонка",
    )
    composer = ui_page_system.locator("sync-message-composer")
    await expect(composer).to_be_visible()
    await composer.locator('textarea[data-canon="composer"]').fill(main_text)
    await composer.locator('button.send').click()
    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(main_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step("Сообщение из основного чата отправлено", ui_page_system)

    await _click_channel_call_button(ui_page_system)
    overlay = ui_page_system.locator("sync-call-overlay-modal")
    await expect(overlay).to_be_visible(timeout=30_000)
    await _ensure_overlay_chat_open(overlay)
    await expect(overlay.locator(".chat-text").get_by_text(main_text, exact=True)).to_be_visible(timeout=30_000)

    await overlay.locator("textarea.chat-input").fill(overlay_text)
    await overlay.locator("button.chat-send").click()
    await expect(overlay.locator(".chat-text").get_by_text(overlay_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step("Чат в оверлее принимает и отправляет сообщения", ui_page_system)

    await overlay.locator("button.ctrl.hangup").click()
    await expect(ui_page_system.locator("sync-app")).not_to_have_attribute("data-call-active", "", timeout=30_000)
    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(overlay_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step("Сообщение из оверлея видно в основном чате канала", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="adhoc-call-visible-channel",
    title="Sync: ad-hoc звонок использует обычный видимый канал",
    description=(
        "Кнопка «Создать Sync» создаёт канал встречи с читаемым именем (дата и время), чат в оверлее работает, "
        "а после переключения каналов сообщения встречи сохраняются в этом канале."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_adhoc_call_channel_is_visible_and_survives_channel_switch(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    base_channel_name = f"Основной канал {unique_id}"
    adhoc_text = f"Adhoc сообщение {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="adhoc")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Основной канал",
    )

    await ui_page_system.locator("sync-chat-list .platform-namespace-trailing-action-btn").first.click()
    overlay = ui_page_system.locator("sync-call-overlay-modal")
    await expect(overlay).to_be_visible(timeout=30_000)
    await _ensure_overlay_chat_open(overlay)

    await overlay.locator("textarea.chat-input").fill(adhoc_text)
    await overlay.locator("button.chat-send").click()
    await expect(overlay.locator(".chat-text").get_by_text(adhoc_text, exact=True)).to_be_visible(
        timeout=30_000
    )

    header_title = (
        await ui_page_system.locator("sync-channel-page sync-chat-header .title").first.inner_text()
    ).strip()
    assert not header_title.startswith("meet_")
    assert any(ch.isdigit() for ch in header_title)
    await scenario.step("Ad-hoc встреча создала видимый канал с именем по дате/времени", ui_page_system)

    await overlay.locator("button.ctrl.hangup").click()
    await expect(ui_page_system.locator("sync-app")).not_to_have_attribute("data-call-active", "", timeout=30_000)

    await sync_sidebar_channel_nav(ui_page_system, base_channel_name).click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()
    await sync_sidebar_channel_nav(ui_page_system, header_title).click()
    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(adhoc_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step("После переключения каналов сообщения ad-hoc канала сохранены", ui_page_system)

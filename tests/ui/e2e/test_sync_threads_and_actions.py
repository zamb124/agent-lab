"""E2E: треды и действия с сообщением (ответ, реакция, редактирование, удаление)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_channel_id_by_name,
    sync_api_find_message_id_with_text,
    sync_api_react_to_message,
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


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


async def _seed_topic_channel(
    sync_ui: AppUI,
    page: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, page, unique_id, suffix="threads")
    await sync_e2e_create_topic_channel_and_open(page, unique_id, channel_prefix="Канал тредов")


@pytest.mark.scenario(
    service="sync",
    tag="threads",
    doc_slug="thread-reply-drawer",
    title="Sync: панель тредов после ответа на сообщение",
    description=(
        "Пользователь отвечает на сообщение в основной ленте и открывает панель «Треды»: "
        "заголовок и область списка отображаются (список может быть пустым, если thread_id "
        "ещё не задан у сообщений в ленте)."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_reply_opens_thread_in_drawer(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    root_text = f"Корень треда {unique_id}"
    reply_text = f"Ответ в треде {unique_id}"

    await _seed_topic_channel(sync_ui, ui_page_system, unique_id)
    await scenario.step("Созданы пространство и канал", ui_page_system)

    composer = ui_page_system.locator("sync-message-composer")
    await composer.locator('textarea[data-canon="composer"]').fill(root_text)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(root_text, exact=True)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Отправлено корневое сообщение", ui_page_system)

    bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=root_text)
    await _open_message_context_menu(ui_page_system, bubble)
    await _click_context_item(ui_page_system, "Открыть тред", "Open thread")
    thread_drawer = ui_page_system.locator("sync-thread-drawer")
    await expect(thread_drawer).to_have_attribute("open", "", timeout=15_000)
    thread_composer = thread_drawer.locator("sync-message-composer")
    await thread_composer.locator('textarea[data-canon="composer"]').fill(reply_text)
    await thread_composer.locator('button.send').click()
    await expect(
        thread_drawer.locator("sync-message-bubble").get_by_text(reply_text, exact=True)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Открыт тред и отправлен ответ", ui_page_system)

    await expect(thread_drawer.locator(".header")).to_be_visible()
    await scenario.step("Открыта панель тредов", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="reaction-edit-message",
    title="Sync: реакция и редактирование своего сообщения",
    description=(
        "Сообщение отправляется из UI; реакция ставится через API; после перезагрузки видна метка "
        "реакции; редактирование текста выполняется в UI."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_reacts_and_edits_own_message(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    first_text = f"Текст до правки {unique_id}"
    edited_text = f"Исправлено {unique_id}"

    await _seed_topic_channel(sync_ui, ui_page_system, unique_id)

    composer = ui_page_system.locator("sync-message-composer")
    await composer.locator('textarea[data-canon="composer"]').fill(first_text)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(first_text, exact=True)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Сообщение отправлено", ui_page_system)

    channel_name_only = f"Канал тредов {unique_id}"
    channel_id = await sync_api_channel_id_by_name(sync_ui.origin, auth_token_system, channel_name_only)
    message_id = await sync_api_find_message_id_with_text(
        sync_ui.origin, auth_token_system, channel_id, first_text
    )
    await sync_api_react_to_message(
        sync_ui.origin, auth_token_system, channel_id, message_id, "👍"
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await sync_sidebar_channel_nav(ui_page_system, channel_name_only).click()
    await expect(ui_page_system.locator("sync-message-bubble .reaction").first).to_be_visible(
        timeout=30_000
    )
    await scenario.step("Поставлена реакция", ui_page_system)

    bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=first_text)
    await _open_message_context_menu(ui_page_system, bubble)
    await _click_context_item(ui_page_system, "Редактировать", "Edit")
    await composer.locator('textarea[data-canon="composer"]').fill(edited_text)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(edited_text, exact=True)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Текст сообщения изменён", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="delete-own-message",
    title="Sync: удаление своего сообщения",
    description="Пользователь удаляет своё сообщение через контекстное меню.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_deletes_own_message(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    msg_text = f"Удалить это {unique_id}"

    await _seed_topic_channel(sync_ui, ui_page_system, unique_id)

    composer = ui_page_system.locator("sync-message-composer")
    await composer.locator('textarea[data-canon="composer"]').fill(msg_text)
    await composer.locator('button.send').click()
    bubble = ui_page_system.locator("sync-message-bubble").filter(has_text=msg_text)
    await expect(bubble).to_be_visible(timeout=30_000)
    await scenario.step("Сообщение для удаления в ленте", ui_page_system)

    await _open_message_context_menu(ui_page_system, bubble)
    await _click_context_item(ui_page_system, "Удалить", "Delete")
    await expect(bubble).to_be_hidden(timeout=30_000)
    await scenario.step("Сообщение исчезло из ленты", ui_page_system)

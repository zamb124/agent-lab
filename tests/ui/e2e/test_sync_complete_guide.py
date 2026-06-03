"""E2E-инструкция: полный рабочий маршрут по сервису Sync."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_api_add_channel_member,
    sync_api_channel_id_by_name,
    sync_api_post_plain_message,
    sync_e2e_click_create_channel,
    sync_e2e_click_platform_button,
    sync_e2e_expect_ws_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
    sync_sidebar_channel_settings_gear,
)
from tests.ui.harness import AppUI
from tests.ui.personas import UiTestUser
from tests.ui.scenario_doc import ScenarioRecorder

# Минимальный PNG 1x1. Нужен только как реальное вложение для проверки upload flow.
_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


async def _send_text_message(page: Page, text: str) -> None:
    composer = page.locator("sync-message-composer").first
    await expect(composer).to_be_visible(timeout=30_000)
    await composer.locator('textarea[data-canon="composer"]').fill(text)
    await composer.locator("button.send").click()
    await expect(
        page.locator("sync-message-bubble").get_by_text(text, exact=True)
    ).to_be_visible(timeout=45_000)


async def _open_message_context_menu(page: Page, text: str) -> None:
    bubble = page.locator("sync-message-bubble").filter(has_text=text).first
    await expect(bubble).to_be_visible(timeout=30_000)
    await bubble.click(button="right")
    await expect(page.locator("sync-message-context-menu")).to_have_attribute(
        "open",
        "",
        timeout=10_000,
    )


async def _click_context_item(page: Page, *labels: str) -> None:
    pattern = re.compile("|".join(re.escape(label) for label in labels))
    item = page.locator("sync-message-context-menu").locator(".item").filter(
        has_text=pattern
    ).first
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()


@pytest.mark.scenario(
    service="sync",
    tag="general",
    doc_slug="sync-complete-guide",
    title="Sync: полная инструкция по сервису",
    description=(
        "Длинная инструкция по основному рабочему маршруту Sync: пространство, канал, "
        "сообщения, упоминания, вложения, меню сообщения, закрепы, треды, настройки "
        "канала, профиль участника и реальные realtime-обновления."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_sync_complete_service_guide(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
    auth_token_system_user2: str,
    ui_user_system_member: UiTestUser,
    tmp_path: Path,
) -> None:
    peer_uid = ui_user_system_member.user_id
    if not isinstance(peer_uid, str) or peer_uid == "":
        raise AssertionError("ui_user_system_member.user_id обязателен для полной инструкции.")

    channel_name = f"Полная инструкция {unique_id}"
    intro_text = f"Стартовая заметка {unique_id}"
    mention_text_tail = "посмотри, пожалуйста"
    attachment_caption = f"Скрин к обсуждению {unique_id}"
    reply_text = f"Ответ в треде {unique_id}"
    peer_message_text = f"Сообщение коллеги {unique_id}"

    await ui_page_system.add_init_script(
        """
        (() => {
            window.localStorage.setItem('platform_locale', 'ru');
            document.cookie = 'language=ru; path=/; SameSite=Lax';
            document.documentElement.lang = 'ru';
        })();
        """
    )

    await sync_e2e_open_with_namespace(
        sync_ui,
        ui_page_system,
        unique_id,
        suffix="full",
    )
    await sync_e2e_expect_ws_open(ui_page_system)
    await scenario.step(
        "Открыт Sync в выбранном пространстве",
        ui_page_system,
        details=(
            "На первом экране важно проверить три зоны интерфейса:\n\n"
            "- слева находится список чатов, поиск и переключатель области поиска;\n"
            "- сверху у списка выбранное пространство, карандаш настроек и кнопка встречи;\n"
            "- в центре показаны карточки каналов выбранного пространства.\n\n"
            "Пространство в Sync — это платформенный namespace. Оно общее для сервисов "
            "платформы, а Sync хранит в нём только свои настройки: авто-расшифровку "
            "голосовых и режим «речь звонка в ленту»."
        ),
    )

    await ui_page_system.locator("platform-sidebar-namespace-select button.btn-edit").click()
    namespace_modal = ui_page_system.locator("sync-namespace-modal")
    await expect(namespace_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открыты Sync-настройки пространства",
        ui_page_system,
        details=(
            "Карандаш рядом с пространством не создаёт и не переименовывает namespace. "
            "Он открывает именно Sync-настройки выбранного пространства.\n\n"
            "- «Авто-транскрипция голосовых» включает STT для новых голосовых сообщений "
            "в каналах этого пространства.\n"
            "- «Речь звонка в ленту» публикует сегменты речи участников звонка в ленту "
            "канала, когда backend и LiveKit egress настроены.\n\n"
            "Эти значения работают как дефолты пространства; у конкретного канала их "
            "можно переопределить в настройках канала."
        ),
    )
    for index in range(2):
        switch = namespace_modal.locator("platform-switch").nth(index)
        await switch.click()
        await expect(switch).to_have_attribute("checked", "", timeout=15_000)
    await sync_e2e_click_platform_button(namespace_modal, "Сохранить", "Save")
    await expect(namespace_modal).to_be_hidden(timeout=30_000)

    await sync_e2e_click_create_channel(ui_page_system)
    create_modal = ui_page_system.locator("sync-channel-create-modal")
    await expect(create_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открыта форма создания канала",
        ui_page_system,
        details=(
            "Канал — основная рабочая единица Sync. В форме есть:\n\n"
            "- «Название» — человекочитаемое имя канала в сайдбаре и карточках;\n"
            "- «Участники» — коллеги, которых можно сразу добавить в канал;\n"
            "- «Приватный канал» — доступ только приглашённым пользователям;\n"
            "- «Авто-расшифровка голосовых» — STT для голосовых сообщений этого канала;\n"
            "- «Речь звонка в ленту» — публикация речи из звонка прямо в чат.\n\n"
            "Если флаги включены и на пространстве, и на канале, итоговое поведение "
            "канала видно пользователю без обращения к API."
        ),
    )
    await create_modal.locator("input.field-pill-input").first.fill(channel_name)
    # В форме создания три переключателя: private, transcribe, speech-to-chat.
    for index in (1, 2):
        await create_modal.locator("platform-switch").nth(index).click()
    await scenario.step(
        "Заполнены название и параметры канала",
        ui_page_system,
        details=(
            "Перед созданием канала полезно сразу включить нужные флаги. "
            "Так команда не будет искать эти настройки после первого звонка или "
            "после первого голосового сообщения."
        ),
    )
    await sync_e2e_click_platform_button(create_modal, "Создать", "Create")
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=45_000
    )
    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Канал создан и открыт",
        ui_page_system,
        details=(
            "Открытый канал состоит из шапки, ленты и композера.\n\n"
            "- В шапке видны аватар, название, подзаголовок, кнопки звонка, видео, "
            "настроек и меню дополнительных действий.\n"
            "- Лента показывает сообщения, даты, статусы доставки, реакции и закрепы.\n"
            "- Композер снизу отправляет текст, файлы, голосовые, упоминания и ответы "
            "в тред."
        ),
    )

    channel_id = await sync_api_channel_id_by_name(
        sync_ui.origin,
        auth_token_system,
        channel_name,
    )
    await sync_api_add_channel_member(
        sync_ui.origin,
        auth_token_system,
        channel_id,
        peer_uid,
    )
    await _expect_company_member_loaded(ui_page_system, peer_uid)

    await _send_text_message(ui_page_system, intro_text)
    await scenario.step(
        "Отправлено первое сообщение",
        ui_page_system,
        details=(
            "Текстовое сообщение уходит через realtime-команду Sync и сразу появляется "
            "в ленте. Для пользователя это обычный чат, но технически событие также "
            "обновляет превью канала, дату последнего сообщения и unread-состояние "
            "у других участников."
        ),
    )

    composer = ui_page_system.locator("sync-message-composer").first
    textarea = composer.locator('textarea[data-canon="composer"]')
    await textarea.click()
    mention_query = peer_uid[-8:]
    await textarea.press_sequentially(f"@{mention_query}")
    popup = composer.locator(".mention-popup")
    await expect(popup).to_be_visible(timeout=30_000)
    member_btn = composer.locator(f'.mention-popup .item[data-user-id="{peer_uid}"]')
    await expect(member_btn).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открыт popup упоминаний",
        ui_page_system,
        details=(
            "Упоминание начинается с символа `@`. Popup ищет участников компании, "
            "а после выбора вставляет технический user_id. В ленте пользователь "
            "видит нормальное имя, потому что Sync преобразует id через список "
            "участников компании.\n\n"
            "Упоминание важно не только визуально: backend валидирует участника канала "
            "и отправляет отдельное mention-уведомление."
        ),
    )
    await member_btn.click()
    await textarea.click()
    await textarea.press_sequentially(mention_text_tail)
    await composer.locator("button.send").click()
    mention_bubble = ui_page_system.locator("sync-message-bubble").last
    await expect(mention_bubble.locator(".body .mention")).to_contain_text(
        "System User 2",
        timeout=45_000,
    )
    await expect(mention_bubble.locator(".body")).to_contain_text(mention_text_tail)
    await scenario.step(
        "Сообщение с упоминанием появилось в ленте",
        ui_page_system,
        details=(
            "После отправки упоминание выглядит как имя человека, а не как `@user_id`. "
            "По клику на такое имя открывается карточка профиля и общие каналы."
        ),
    )

    png_path = tmp_path / "sync-guide.png"
    png_path.write_bytes(_MIN_PNG)
    file_input = composer.locator("input#photopick")
    await expect(file_input).to_be_attached(timeout=15_000)
    await file_input.set_input_files(str(png_path))
    await expect(composer.locator(".att").filter(has_text="sync-guide.png")).to_be_visible(
        timeout=30_000
    )
    await textarea.fill(attachment_caption)
    await composer.locator("button.send").click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(
            attachment_caption,
            exact=True,
        )
    ).to_be_visible(timeout=60_000)
    await expect(
        ui_page_system.locator("sync-message-bubble .image-wrap img").last
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Отправлено сообщение с изображением",
        ui_page_system,
        details=(
            "Кнопка вложения загружает файл в файловый backend и добавляет его в "
            "сообщение как контент-блок. Для изображений Sync показывает превью, "
            "для документов — строку файла со скачиванием. Подпись сообщения остаётся "
            "обычным текстовым блоком."
        ),
    )

    await _open_message_context_menu(ui_page_system, intro_text)
    await scenario.step(
        "Открыто меню сообщения",
        ui_page_system,
        details=(
            "Контекстное меню открывается правым кликом по сообщению. В нём есть "
            "быстрые реакции и действия:\n\n"
            "- «Ответить» — включает режим ответа в композере;\n"
            "- «Открыть тред» — создаёт или открывает ветку обсуждения;\n"
            "- «Редактировать» — доступно для своих текстовых сообщений;\n"
            "- «Скопировать» — копирует текст;\n"
            "- «Переслать» — открывает выбор канала назначения;\n"
            "- «Закрепить» — добавляет сообщение в верхнюю полоску закрепов;\n"
            "- «Удалить» — доступно для своих сообщений."
        ),
    )
    await _click_context_item(ui_page_system, "Закрепить", "Pin")
    await expect(ui_page_system.locator("sync-pin-strip .row")).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Сообщение закреплено",
        ui_page_system,
        details=(
            "Закрепы хранятся на канале. Полоска сверху показывает превью текущего "
            "закреплённого сообщения и счётчик. Клик по полоске прокручивает ленту "
            "к закрепу; если закрепов несколько, переход идёт по кругу."
        ),
    )

    await _open_message_context_menu(ui_page_system, intro_text)
    await _click_context_item(ui_page_system, "Открыть тред", "Open thread")
    thread_drawer = ui_page_system.locator("sync-thread-drawer")
    await expect(thread_drawer).to_have_attribute("open", "", timeout=30_000)
    thread_composer = thread_drawer.locator("sync-message-composer")
    await thread_composer.locator('textarea[data-canon="composer"]').fill(reply_text)
    await thread_composer.locator("button.send").click()
    await expect(
        thread_drawer.locator("sync-message-bubble").get_by_text(reply_text, exact=True)
    ).to_be_visible(timeout=45_000)
    await scenario.step(
        "Открыт тред и отправлен ответ",
        ui_page_system,
        details=(
            "Тред — боковая панель справа от основной ленты. Он нужен, когда обсуждение "
            "не должно засорять общий канал. Ответы внутри треда связаны с корневым "
            "сообщением, но основной чат остаётся доступен."
        ),
    )
    await thread_drawer.locator("button.close").click()
    await expect(thread_drawer).not_to_have_attribute("open", "", timeout=15_000)

    await sync_sidebar_channel_settings_gear(ui_page_system, channel_name).click()
    settings_modal = ui_page_system.locator("sync-channel-edit-modal")
    await expect(settings_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открыты настройки канала",
        ui_page_system,
        details=(
            "Настройки канала отличаются от настроек пространства. Здесь меняются "
            "локальные параметры конкретного канала:\n\n"
            "- имя и аватар;\n"
            "- «Не беспокоить» для уведомлений;\n"
            "- авто-транскрипция голосовых именно в этом канале;\n"
            "- «речь звонка в ленту» именно для этого канала;\n"
            "- список участников и кнопка добавления новых участников.\n\n"
            "Если пользователь не видит канал в сайдбаре, первым делом проверьте, "
            "добавлен ли он в участники канала."
        ),
    )
    await sync_e2e_click_platform_button(settings_modal, "Сохранить", "Save")
    await expect(settings_modal).to_be_hidden(timeout=30_000)

    await sync_api_post_plain_message(
        sync_ui.origin,
        auth_token_system_user2,
        channel_id,
        peer_message_text,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await sync_e2e_expect_ws_open(ui_page_system)
    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(
            peer_message_text,
            exact=True,
        )
    ).to_be_visible(timeout=60_000)
    peer_bubble = ui_page_system.locator("sync-message-bubble").filter(
        has_text=peer_message_text
    )
    await peer_bubble.locator(".sender").click()
    user_modal = ui_page_system.locator("platform-user-info-modal")
    await expect(user_modal).to_be_visible(timeout=30_000)
    await expect(user_modal.get_by_text("System User 2", exact=False)).to_be_visible()
    await expect(user_modal.get_by_text(re.compile(r"Каналы вместе|Shared channels"))).to_be_visible()
    await scenario.step(
        "Открыта карточка профиля участника",
        ui_page_system,
        details=(
            "Профиль открывается из аватара отправителя или из `@mention`. В карточке "
            "видно имя участника и общие каналы. Это быстрый способ понять, где ещё "
            "вы пересекаетесь с человеком, и перейти в нужный канал без ручного поиска."
        ),
    )

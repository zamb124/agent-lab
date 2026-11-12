"""Документационный сценарий Wiki: история версий страницы.

Маршрут пользователя: отредактировать страницу, открыть «Историю»,
сравнить ревизию с текущей версией и при необходимости откатиться.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.wiki_e2e_helpers import (
    wiki_e2e_open_with_namespace,
    wiki_e2e_title_input,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="wiki",
    tag="pages",
    doc_slug="page-version-history",
    title="История версий: посмотреть и откатить страницу",
    title_en="Version history: review and restore a page",
    description=(
        "**Для чего:** эта инструкция покажет, где лежат все прошлые версии "
        "страницы и как вернуть любую из них одним действием.\n\n"
        "**Какие проблемы решает:** случайно удалили абзац или коллега "
        "переписал раздел — текст не потерян, всегда можно посмотреть, что "
        "было, и откатиться.\n\n"
        "**Результат:** вы открываете историю, сравниваете ревизию с "
        "текущим текстом и восстанавливаете нужную версию."
    ),
    description_en=(
        "**What for:** this guide shows where all previous versions of a "
        "page live and how to bring any of them back in one action.\n\n"
        "**Problems it solves:** if a paragraph is deleted by accident or a "
        "colleague rewrote a section, nothing is lost — you can see what "
        "changed and roll back.\n\n"
        "**Result:** you open history, compare a revision with the current "
        "text, and restore the version you need."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_wiki_page_version_history(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    frontend_di,
) -> None:
    page = ui_page_system
    await wiki_e2e_open_with_namespace(
        wiki_ui, page, unique_id, suffix="hist", di=frontend_di
    )
    await page.set_viewport_size(_DESKTOP)

    await page.locator("wiki-sidebar [data-wiki-create-page]").click()
    title_input = wiki_e2e_title_input(page)
    await expect(title_input).to_be_visible(timeout=30_000)
    await title_input.fill(f"Регламент {unique_id[:6]}")

    editor = page.locator("wiki-page-view .pm-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.click()
    await page.keyboard.type("Первая редакция регламента")
    save_state = page.locator("wiki-page-view .save-state")
    await expect(save_state).to_have_attribute("data-state", "done", timeout=30_000)

    await page.keyboard.press("Enter")
    await page.keyboard.type("Вторая редакция: добавили пункт про согласование")
    await expect(save_state).to_have_attribute("data-state", "done", timeout=30_000)

    await page.keyboard.press("Enter")
    await page.keyboard.type("Третья редакция: убрали лишнее и поправили стиль")
    await expect(save_state).to_have_attribute("data-state", "done", timeout=30_000)
    await scenario.step(
        "Отредактируйте страницу пару раз",
        page,
        screenshot_name="page-edited",
        label_en="Edit the page a couple of times",
        details=(
            "Каждое сохранение запоминает версию страницы. Мы написали два "
            "варианта текста — теперь в истории их две ревизии."
        ),
        details_en=(
            "Every save records a page version. We wrote two variants of "
            "the text, so the history now holds two revisions."
        ),
    )

    await page.locator("wiki-page-view [data-wiki-page-menu]").click()
    await page.locator('platform-menu [data-menu-item="history"]').click()
    history_page = page.locator("wiki-history-page")
    await expect(history_page).to_be_visible(timeout=30_000)
    revisions = history_page.locator(".revision")
    await expect(revisions.first).to_be_visible(timeout=30_000)
    await expect(revisions.nth(1)).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Историю» в меню страницы",
        page,
        screenshot_name="history-list",
        label_en="Open History from the page menu",
        details=(
            "В меню страницы выберите «История» — справа список версий с "
            "датой и автором, слева предпросмотр выбранной редакции."
        ),
        details_en=(
            "Choose History in the page menu — the revision list with date "
            "and author is on one side, the selected revision preview on "
            "the other."
        ),
    )

    await revisions.first.click()
    await expect(history_page.locator(".revision.is-selected")).to_have_count(
        1, timeout=15_000
    )
    await expect(history_page.locator(".diff-line").first).to_be_visible(
        timeout=15_000
    )
    await scenario.step(
        "Выберите старую версию и сравните",
        page,
        screenshot_name="old-revision-preview",
        label_en="Pick the old revision and compare",
        details=(
            "Кликните по более ранней версии — справа подсвечивается разница "
            "с текущим текстом: что убрали, а что добавили. Так вы точно "
            "видите, к чему вернётся страница."
        ),
        details_en=(
            "Click an earlier revision — the difference with the current "
            "text is highlighted on the right: what was removed and what "
            "was added. You see exactly what the page will return to."
        ),
    )

    await history_page.locator("[data-wiki-restore]").click()
    confirm = page.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=15_000)
    await confirm.locator(".btn-primary").click()
    await expect(editor).to_be_visible(timeout=30_000)
    await expect(editor).to_contain_text("Первая редакция регламента")
    await expect(editor).to_contain_text("добавили пункт про согласование")
    await expect(editor).not_to_contain_text(
        "убрали лишнее и поправили стиль"
    )
    await scenario.step(
        "Нажмите «Восстановить» — страница откатится",
        page,
        screenshot_name="revision-restored",
        label_en="Press Restore — the page rolls back",
        details=(
            "Кнопка «Восстановить» возвращает выбранную версию: страница "
            "снова выглядит как перед последней правкой. Сам откат тоже "
            "попадает в историю — ничего не теряется."
        ),
        details_en=(
            "The Restore button brings back the chosen version: the page "
            "looks like it did before the last edit. The rollback itself "
            "is recorded in history too — nothing is lost."
        ),
    )

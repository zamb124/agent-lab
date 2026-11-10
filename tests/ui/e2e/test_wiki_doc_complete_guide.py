"""Документационный сценарий Wiki: полный маршрут страницы.

Маршрут пользователя: дерево → новая страница → заголовок и блоки текста →
автосохранение → публикация для компании через доступ.
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
    tag="getting-started",
    doc_slug="wiki-complete-guide",
    title="Полный маршрут: от пустого дерева до опубликованной страницы",
    title_en="Complete route: from empty tree to published page",
    description=(
        "**Для чего:** завести корпоративную базу знаний — пройти весь "
        "путь от пустого дерева до страницы, видимой всей компании.\n\n"
        "**Какие проблемы решает:** регламенты и инструкции лежат в чатах "
        "и файлах. Здесь вы увидите, как за минуту появляется аккуратная "
        "страница с заголовками, списками и общим доступом.\n\n"
        "**Результат:** страница написана, автосохранена и открыта для "
        "всей компании — коллеги уже могут её читать."
    ),
    description_en=(
        "**Purpose:** build a company knowledge base — walk the full "
        "route from an empty tree to a page visible to the whole "
        "company.\n\n"
        "**Problems solved:** rules and instructions scattered in chats "
        "and files. Here you will see a tidy page with headings, lists "
        "and shared access appear in a minute.\n\n"
        "**Result:** the page is written, autosaved and opened to the "
        "whole company — colleagues can already read it."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_wiki_complete_guide(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    frontend_di,
) -> None:
    page = ui_page_system
    await wiki_e2e_open_with_namespace(
        wiki_ui, page, unique_id, suffix="guide", di=frontend_di
    )
    await page.set_viewport_size(_DESKTOP)
    await scenario.step(
        "Дерево базы знаний",
        page,
        screenshot_name="wiki-tree",
        label_en="Knowledge base tree",
        details=(
            "Wiki открывается деревом страниц: слева — разделы и вложенные "
            "страницы, справа — текст. Нажмите «+» у дерева, чтобы создать "
            "первую страницу."
        ),
        details_en=(
            "Wiki opens with a page tree: sections and nested pages on "
            "the left, content on the right. Click + near the tree to "
            "create the first page."
        ),
    )

    await page.locator("wiki-sidebar [data-wiki-create-page]").click()
    title_input = wiki_e2e_title_input(page)
    await expect(title_input).to_be_visible(timeout=30_000)
    await scenario.step(
        "Создана пустая страница",
        page,
        screenshot_name="empty-page",
        label_en="Empty page created",
        details=(
            "Новая страница сразу открыта: поле заголовка сверху, пустой "
            "текст ниже. Введите название — оно появится в дереве."
        ),
        details_en=(
            "The new page opens right away: a title field on top, empty "
            "body below. Type a title — it appears in the tree."
        ),
    )

    title = f"Регламент офиса {unique_id[:6]}"
    await title_input.fill(title)
    editor = page.locator("wiki-page-view .pm-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.click()
    await page.keyboard.type("# Порядок в офисе")
    await page.keyboard.press("Enter")
    await page.keyboard.type("Короткий регламент для всех сотрудников.")
    await page.keyboard.press("Enter")
    await page.keyboard.type("- Ключи от кабинета бронируем в чате")
    await page.keyboard.press("Enter")
    await page.keyboard.type("Гостей встречаем на ресепшене")

    save_state = page.locator("wiki-page-view .save-state")
    await expect(save_state).to_have_attribute(
        "data-state", "done", timeout=30_000
    )
    await scenario.step(
        "Заголовок, список и автосохранение",
        page,
        screenshot_name="blocks-saved",
        label_en="Heading, list and autosave",
        details=(
            "Текст набирается как в обычном редакторе: «# » делает "
            "заголовок, «- » — пункт списка. Сохранять вручную не нужно — "
            "индикатор сверху показывает, что всё записано."
        ),
        details_en=(
            "Type like in a regular editor: '# ' makes a heading, '- ' a "
            "list item. No manual save needed — the indicator on top "
            "shows everything is stored."
        ),
    )

    await page.locator("wiki-page-view [data-wiki-page-menu]").click()
    access_entry = page.locator("platform-menu [data-menu-item='access']")
    await expect(access_entry).to_be_visible(timeout=10_000)
    await access_entry.click()
    access_modal = page.locator("wiki-page-access-modal")
    await expect(access_modal).to_be_visible(timeout=15_000)
    await scenario.step(
        "Открываем доступ для компании",
        page,
        screenshot_name="access-modal",
        label_en="Open access for the company",
        details=(
            "В меню страницы есть пункт «Доступ»: здесь видно, кто может "
            "читать и править, и включается видимость для всей компании. "
            "Включите переключатель — и страница появится у коллег."
        ),
        details_en=(
            "The page menu has an Access entry: here you see who can "
            "read and edit, and enable company-wide visibility. Turn the "
            "switch on — and the page appears for colleagues."
        ),
    )

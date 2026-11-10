"""Документационный сценарий Wiki: блочный редактор.

Маршрут пользователя: писать текст и превращать его в заголовки, списки,
цитаты и код короткими командами прямо при наборе.
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
    doc_slug="editor-blocks",
    title="Блочный редактор: заголовки, списки, цитаты и код",
    title_en="Block editor: headings, lists, quotes and code",
    description=(
        "**Для чего:** оформлять страницы аккуратно — заголовки, списки, "
        "цитаты и блоки кода без мыши, прямо при наборе.\n\n"
        "**Какие проблемы решает:** сплошной текст читается плохо. "
        "Короткие команды («# », «- », «> », «```») мгновенно превращают "
        "строку в нужный блок.\n\n"
        "**Результат:** страница с заголовком, списком дел, цитатой и "
        "блоком кода — набранная без единого клика по панели форматов."
    ),
    description_en=(
        "**Purpose:** format pages cleanly — headings, lists, quotes and "
        "code blocks without the mouse, right while typing.\n\n"
        "**Problems solved:** a wall of text is hard to read. Short "
        "commands ('# ', '- ', '> ', '```') instantly turn a line into "
        "the right block.\n\n"
        "**Result:** a page with a heading, to-do list, quote and code "
        "block — typed without a single toolbar click."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_wiki_editor_blocks(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    frontend_di,
) -> None:
    page = ui_page_system
    await wiki_e2e_open_with_namespace(
        wiki_ui, page, unique_id, suffix="blocks", di=frontend_di
    )
    await page.set_viewport_size(_DESKTOP)

    await page.locator("wiki-sidebar [data-wiki-create-page]").click()
    title_input = wiki_e2e_title_input(page)
    await expect(title_input).to_be_visible(timeout=30_000)
    await title_input.fill(f"Шпаргалка по блокам {unique_id[:6]}")

    editor = page.locator("wiki-page-view .pm-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.click()
    await page.keyboard.type("# Блоки редактора")
    await page.keyboard.press("Enter")
    await page.keyboard.type("> Хорошая страница читается с первого взгляда")
    await page.keyboard.press("Enter")
    await page.keyboard.press("Enter")
    await page.keyboard.type("- Заголовок через #")
    await page.keyboard.press("Enter")
    await page.keyboard.type("Список через дефис")
    await page.keyboard.press("Enter")
    await page.keyboard.press("Enter")
    await page.keyboard.type("```python ")
    code_area = editor.locator(".pm-code-block .cm-content")
    await expect(code_area).to_be_visible(timeout=10_000)
    await code_area.click()
    await page.keyboard.type("print('hello, wiki')")

    save_state = page.locator("wiki-page-view .save-state")
    await expect(save_state).to_have_attribute(
        "data-state", "done", timeout=30_000
    )
    await scenario.step(
        "Набираем блоки короткими командами",
        page,
        screenshot_name="blocks-typed",
        label_en="Typing blocks with short commands",
        details=(
            "Редактор понимает разметку при наборе: «# » — заголовок, "
            "«> » — цитата, «- » — список, «```» — блок кода. Строка "
            "превращается в блок сразу после пробела."
        ),
        details_en=(
            "The editor understands markup while typing: '# ' heading, "
            "'> ' quote, '- ' list, '```' code block. A line becomes a "
            "block right after the space."
        ),
    )

    await expect(editor.locator("h1")).to_contain_text("Блоки редактора")
    await expect(editor.locator("blockquote")).to_be_visible()
    await expect(editor.locator("ul li").first).to_be_visible()
    await expect(code_area).to_contain_text("hello, wiki", timeout=10_000)
    await scenario.step(
        "Всё превратилось в блоки",
        page,
        screenshot_name="blocks-rendered",
        label_en="Everything became blocks",
        details=(
            "Вот та же страница глазами читателя: крупный заголовок, "
            "цитата с полосой, маркированный список и подсвеченный код. "
            "Каждый блок можно перетаскивать и менять местами."
        ),
        details_en=(
            "Here is the same page through the reader's eyes: a big "
            "heading, a striped quote, a bullet list and highlighted "
            "code. Every block can be dragged and reordered."
        ),
    )

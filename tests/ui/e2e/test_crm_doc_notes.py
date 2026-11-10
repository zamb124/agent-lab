"""Документационный сценарий CRM: ежедневные заметки.

Маршрут пользователя: открыть дневник, написать заметку о рабочем дне
в markdown-редакторе и сохранить — запись остаётся в ленте.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="crm",
    tag="notes",
    doc_slug="daily-notes",
    title="Ежедневные заметки: дневник рабочего дня",
    title_en="Daily notes: working day diary",
    description=(
        "**Для чего:** фиксировать итоги дня — звонки, договорённости, "
        "мысли — пока они свежие, и находить их потом по дате.\n\n"
        "**Какие проблемы решает:** договорённости теряются в чатах и "
        "голове. Заметка за день занимает минуту, а потом легко "
        "вспомнить, что и когда обсуждали.\n\n"
        "**Результат:** заметка сохранена и лежит в ленте за свою дату — "
        "к ней можно вернуться и привязать к записям."
    ),
    description_en=(
        "**Purpose:** capture the day's outcomes — calls, agreements, "
        "thoughts — while fresh, and find them later by date.\n\n"
        "**Problems solved:** agreements get lost in chats and memory. A "
        "daily note takes a minute, then it is easy to recall what was "
        "discussed and when.\n\n"
        "**Result:** the note is saved in the feed under its date — you "
        "can come back and link it to records."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_daily_notes(
    crm_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    page = ui_page_system
    note_text = f"Созвон с поставщиком {unique_id[:4]}: договорились о скидке 10%."

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)

    await page.goto(f"{crm_ui.origin}/crm/notes", wait_until="domcontentloaded")
    notes_page = page.locator("crm-daily-notes-page")
    await expect(notes_page).to_be_visible(timeout=60_000)
    await scenario.step(
        "Дневник заметок",
        page,
        screenshot_name="notes-feed",
        label_en="Notes diary",
        details=(
            "Раздел «Заметки» — лента записей по дням. Сверху — выбор "
            "периода и диктовка голосом, кнопка «Добавить заметку» "
            "открывает редактор."
        ),
        details_en=(
            "The Notes section is a feed of entries by day. On top — a "
            "period picker and voice dictation; the Add note button "
            "opens the editor."
        ),
    )

    create_btn = notes_page.locator(".cta-btn").first
    await expect(create_btn).to_be_visible(timeout=15_000)
    await create_btn.click()

    note_page = page.locator("crm-note-page")
    await expect(note_page).to_be_visible(timeout=30_000)
    editor = note_page.locator("platform-markdown-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.locator("[contenteditable], textarea, .pm-editor").first.click()
    await page.keyboard.type(note_text)
    await scenario.step(
        "Пишем заметку",
        page,
        screenshot_name="note-editor",
        label_en="Writing a note",
        details=(
            "Редактор поддерживает разметку: заголовки, списки, ссылки на "
            "записи через «@». Пишите как в обычном блокноте — что "
            "обсуждали, о чём договорились, что сделать завтра."
        ),
        details_en=(
            "The editor supports markup: headings, lists, record links "
            "via @. Write like in a regular notepad — what was "
            "discussed, what was agreed, what to do tomorrow."
        ),
    )

    save_btn = note_page.locator("button.pill-btn").last
    await expect(save_btn).to_be_enabled(timeout=10_000)
    await save_btn.click()
    await expect(
        note_page.get_by_text(note_text, exact=False)
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Заметка сохранена",
        page,
        screenshot_name="note-saved",
        label_en="Note saved",
        details=(
            "После сохранения заметка открывается в режиме чтения — "
            "дата проставлена автоматически. Ниже можно привязать её к "
            "записям клиентов и сделок."
        ),
        details_en=(
            "After saving the note opens in read mode — the date is set "
            "automatically. Below you can link it to customer and deal "
            "records."
        ),
    )

    await page.goto(f"{crm_ui.origin}/crm/notes", wait_until="domcontentloaded")
    await expect(notes_page).to_be_visible(timeout=60_000)
    await expect(
        notes_page.get_by_text(note_text, exact=False)
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Заметка в ленте",
        page,
        screenshot_name="note-in-feed",
        label_en="Note in the feed",
        details=(
            "Заметка появилась в ленте под своей датой. Дальше её можно "
            "дополнить, привязать к клиенту или попросить платформу "
            "разобрать её на записи."
        ),
        details_en=(
            "The note appeared in the feed under its date. You can amend "
            "it, link it to a customer, or ask the platform to break it "
            "down into records."
        ),
    )

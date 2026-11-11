"""Документационные сценарии CRM: настройка пространства.

Маршруты пользователя: библиотека шаблонов пространств — что входит
в готовый шаблон и из каких типов записей он собран.
"""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="crm",
    tag="setup",
    doc_slug="templates-library",
    title="Библиотека шаблонов: из чего собрано пространство",
    title_en="Template library: what a space is made of",
    description=(
        "**Для чего:** понять, что даёт готовый шаблон при создании "
        "пространства — какие типы записей и поля появятся внутри.\n\n"
        "**Какие проблемы решает:** шаблоны выглядят как «чёрный ящик». "
        "Библиотека показывает каждый шаблон изнутри: список типов "
        "записей и их поля — можно заранее убедиться, что шаблон "
        "подходит под свои задачи.\n\n"
        "**Результат:** вы знаете, где посмотреть состав шаблона и как "
        "проверить поля типа записи до создания пространства."
    ),
    description_en=(
        "**Purpose:** see what a ready-made template brings to a new "
        "space — which record types and fields appear inside.\n\n"
        "**Problems solved:** templates look like a black box. The "
        "library opens each one: the record-type list and their "
        "fields — so you can check the fit before creating a space.\n\n"
        "**Result:** you know where to inspect a template's contents "
        "and how to verify a record type's fields beforehand."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_templates_library_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{crm_ui.origin}/crm/templates", wait_until="domcontentloaded"
    )
    templates_page = page.locator("crm-templates-page")
    await expect(templates_page).to_be_visible(timeout=60_000)
    tpl_cards = templates_page.locator(".tpl-card")
    await expect(tpl_cards.first).to_be_visible(timeout=60_000)
    await scenario.step(
        "Библиотека шаблонов",
        page,
        screenshot_name="templates-library",
        label_en="Template library",
        details=(
            "Раздел «Настройки → Шаблоны» показывает все готовые "
            "шаблоны пространств. На карточке — название, описание и "
            "число типов записей внутри."
        ),
        details_en=(
            "The Settings → Templates section lists every ready-made "
            "space template. Each card shows a name, a description and "
            "how many record types it contains."
        ),
    )

    sales_card = tpl_cards.filter(has_text=re.compile("B2B|sales|Продаж", re.I))
    if await sales_card.count() == 0:
        sales_card = tpl_cards
    await sales_card.first.click()
    type_cards = templates_page.locator(".type-card")
    await expect(type_cards.first).to_be_visible(timeout=60_000)
    await scenario.step(
        "Состав шаблона",
        page,
        screenshot_name="template-types",
        label_en="Template contents",
        details=(
            "Клик по шаблону раскрывает его состав: справа появляются "
            "все типы записей — Лиды, Контакты, Сделки и другие. "
            "Чипы под типом показывают, в каких пространствах он уже "
            "используется."
        ),
        details_en=(
            "Clicking a template unfolds its contents: the right panel "
            "lists all record types — Leads, Contacts, Deals and more. "
            "Chips under a type show which spaces already use it."
        ),
    )

    edit_type = type_cards.first.get_by_role(
        "button", name=re.compile("Редактировать|Edit")
    )
    await expect(edit_type).to_be_visible(timeout=30_000)
    await edit_type.click()
    type_form = templates_page.locator(".type-form, .panel").last
    await expect(
        templates_page.locator("platform-field").first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Поля типа записи",
        page,
        screenshot_name="template-type-form",
        label_en="Record type fields",
        details=(
            "Кнопка «Редактировать» на карточке типа открывает его "
            "схему: имя, иконку и набор полей записи. Отсюда видно, "
            "какие данные пространство будет собирать по каждому "
            "клиенту или сделке.\n\n"
            "**Итог.** Шаблон — это не «магия», а прозрачный набор "
            "типов и полей: проверили заранее — не будет сюрпризов "
            "после создания пространства."
        ),
        details_en=(
            "The Edit button on a type card opens its schema: name, "
            "icon and the record field set. This shows exactly what "
            "data the space will collect for each customer or deal.\n\n"
            "**Summary.** A template is not magic — it is a "
            "transparent set of types and fields: check it upfront "
            "and there will be no surprises after creating the space."
        ),
    )

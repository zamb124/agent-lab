"""Документационный сценарий CRM: первое пространство и первая запись.

Маршрут пользователя: создать пространство из готового шаблона, открыть его
и завести первую карточку — выбрать тип записи и заполнить имя.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="crm",
    tag="getting-started",
    doc_slug="crm-first-entity",
    title="Первое пространство и первая запись",
    title_en="First space and first record",
    description=(
        "**Для чего:** собрать свою базу контактов и сделок — создать "
        "пространство из готового шаблона и завести первую карточку.\n\n"
        "**Какие проблемы решает:** клиенты в разрозненных таблицах и "
        "заметках. Здесь вы увидите, как за пару минут появляется "
        "структурированная картотека с нужными типами записей.\n\n"
        "**Результат:** пространство с типами Лид, Клиент и Сделка — "
        "и первая карточка клиента внутри."
    ),
    description_en=(
        "**Purpose:** build your own base of contacts and deals — create "
        "a space from a ready-made template and add the first record.\n\n"
        "**Problems solved:** customers scattered across spreadsheets and "
        "notes. Here you will see a structured card index with the right "
        "record types appear in a couple of minutes.\n\n"
        "**Result:** a space with Lead, Account and Deal types — and the "
        "first customer record inside."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_first_entity(
    crm_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    page = ui_page_system
    space_name = f"sales_dept_{unique_id[:6].lower()}"
    entity_name = f"ООО «Ромашка» {unique_id[:4]}"

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)

    await page.goto(f"{crm_ui.origin}/crm/namespaces", wait_until="domcontentloaded")
    await expect(page.locator("crm-namespaces-page")).to_be_visible(timeout=60_000)
    await scenario.step(
        "Список пространств компании",
        page,
        screenshot_name="namespaces-list",
        label_en="Company spaces list",
        details=(
            "Откройте NetWorkle — раздел «Пространства» показывает все "
            "рабочие области компании. Пространство — это отдельная "
            "картотека со своими типами записей. Нажмите «Создать "
            "пространство»."
        ),
        details_en=(
            "Open NetWorkle — the Spaces section shows all company work "
            "areas. A space is a separate card index with its own record "
            "types. Click Create space."
        ),
    )

    create_btn = page.locator("crm-namespaces-page .btn-primary").first
    await create_btn.click()
    modal = page.locator("crm-namespace-modal")
    await expect(modal).to_be_visible(timeout=15_000)

    sales_template = modal.locator(".template-card", has_text="B2B")
    await expect(sales_template).to_be_visible(timeout=15_000)
    await sales_template.click()
    name_field = modal.locator("platform-field").first
    await ui_set_platform_field(name_field, space_name)
    await scenario.step(
        "Выбираем шаблон и имя",
        page,
        screenshot_name="namespace-template",
        label_en="Pick a template and a name",
        details=(
            "Шаблон — это готовый набор типов записей. «B2B-продажи» уже "
            "содержит Лидов, Клиентов и Сделки — ничего настраивать не "
            "нужно. Имя пространства пишется латиницей в одно слово, "
            "например «sales_dept» — так системе проще с ним работать."
        ),
        details_en=(
            "A template is a ready-made set of record types. B2B sales "
            "already includes Leads, Accounts and Deals — nothing to "
            "configure. The space name is a single lowercase latin word "
            "like sales_dept."
        ),
    )

    save_btn = modal.locator(".header-save-btn")
    await expect(save_btn).to_be_enabled(timeout=10_000)
    await save_btn.click()
    await expect(modal).to_be_hidden(timeout=30_000)
    ns_card = page.locator("crm-namespaces-page article.card").filter(
        has_text=space_name
    )
    await expect(ns_card).to_be_visible(timeout=30_000)
    await scenario.step(
        "Пространство создано",
        page,
        screenshot_name="namespace-created",
        label_en="Space created",
        details=(
            f"Пространство «{space_name}» появилось в списке — внутри "
            "уже есть типы записей из шаблона. Нажмите «Открыть», чтобы "
            "войти в него."
        ),
        details_en=(
            f"The space {space_name} appeared in the list — it already "
            "has record types from the template. Click Open to enter it."
        ),
    )

    open_btn = ns_card.locator(".card-actions .btn").last
    await expect(open_btn).to_be_visible(timeout=15_000)
    await open_btn.click()

    await page.goto(f"{crm_ui.origin}/crm/entities", wait_until="domcontentloaded")
    entities_page = page.locator("crm-entities-page")
    await expect(entities_page).to_be_visible(timeout=60_000)
    await scenario.step(
        "Картотека пространства",
        page,
        screenshot_name="entities-empty",
        label_en="Space records",
        details=(
            "Раздел «Записи» — сама картотека. Пока она пустая: нажмите "
            "кнопку создания, чтобы завести первую запись."
        ),
        details_en=(
            "The Records section is the card index itself. It is empty "
            "for now: click the create button to add the first record."
        ),
    )

    create_entity = entities_page.locator(".cta-btn").first
    await expect(create_entity).to_be_visible(timeout=15_000)
    await create_entity.click()

    create_page = page.locator("crm-entity-create-page")
    await expect(create_page).to_be_visible(timeout=30_000)
    contact_type = create_page.locator(".type-card", has_text="Контакт")
    if await contact_type.count() == 0:
        contact_type = create_page.locator(".type-card", has_text="contact")
    await expect(contact_type.first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Выбираем тип записи",
        page,
        screenshot_name="entity-type-pick",
        label_en="Pick a record type",
        details=(
            "Сначала выберите, что за записью стоит: контакт, компания, "
            "сделка или лид. У каждого типа — свой набор полей. Берём "
            "«Контакт»."
        ),
        details_en=(
            "First pick what the record is about: a contact, a company, "
            "a deal or a lead. Each type has its own fields. We pick "
            "Contact."
        ),
    )
    await contact_type.first.click()

    entity_name_field = create_page.locator(
        "crm-entity-card platform-field"
    ).first
    await ui_set_platform_field(entity_name_field, entity_name)
    await scenario.step(
        "Заполняем карточку",
        page,
        screenshot_name="entity-form",
        label_en="Fill in the card",
        details=(
            "Введите имя — этого достаточно для первой записи. Остальные "
            "поля можно заполнить позже прямо в карточке. Нажмите "
            "«Создать»."
        ),
        details_en=(
            "Enter a name — that is enough for the first record. Other "
            "fields can be filled later right in the card. Click Create."
        ),
    )

    save_entity = create_page.locator(".toolbar-pill-primary")
    await expect(save_entity).to_be_enabled(timeout=10_000)
    await save_entity.click()
    await expect(page.locator("crm-entity-detail-page")).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Первая запись готова",
        page,
        screenshot_name="entity-detail",
        label_en="First record is ready",
        details=(
            f"Карточка «{entity_name}» создана и открыта. Сюда можно "
            "добавлять заметки, связи с другими записями и задачи — вся "
            "история клиента в одном месте."
        ),
        details_en=(
            f"The record {entity_name} is created and open. You can add "
            "notes, links to other records and tasks here — the whole "
            "customer history in one place."
        ),
    )


@pytest.mark.scenario(
    service="crm",
    tag="getting-started",
    doc_slug="crm-namespaces-tour",
    title="Что живёт внутри пространства: обзор разделов",
    title_en="What lives inside a space: sections tour",
    description=(
        "**Для чего:** понять, где в NetWorkle что лежит — заметки, "
        "записи, граф связей и AI-предложения.\n\n"
        "**Какие проблемы решает:** после создания пространства непонятно, "
        "куда идти дальше. Этот тур за минуту показывает каждый раздел "
        "и что он даёт в работе.\n\n"
        "**Результат:** вы знаете карту разделов пространства и можете "
        "сознательно выбрать, где вести свою работу."
    ),
    description_en=(
        "**Purpose:** understand where things live in NetWorkle — notes, "
        "records, the relation graph and AI suggestions.\n\n"
        "**Problems solved:** after creating a space it is unclear where "
        "to go next. This tour shows every section in a minute and what "
        "it gives you.\n\n"
        "**Result:** you know the space section map and can consciously "
        "pick where to do your work."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_namespaces_tour(
    crm_ui: AppUI,
    ui_page_system: Page,
    scenario: ScenarioRecorder,
) -> None:
    page = ui_page_system

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)

    await page.goto(f"{crm_ui.origin}/crm/notes", wait_until="domcontentloaded")
    await expect(page.locator("crm-daily-notes-page")).to_be_visible(timeout=60_000)
    await scenario.step(
        "Заметки дня",
        page,
        screenshot_name="daily-notes",
        label_en="Daily notes",
        details=(
            "Раздел «Заметки» — рабочий дневник: короткие записи по "
            "клиентам, звонкам и делам. Заметку можно привязать к записи, "
            "и она останется в истории клиента навсегда."
        ),
        details_en=(
            "The Notes section is a working diary: short entries about "
            "customers, calls and tasks. A note can be linked to a record "
            "and stays in the customer history forever."
        ),
    )

    await page.goto(f"{crm_ui.origin}/crm/entities", wait_until="domcontentloaded")
    await expect(page.locator("crm-entities-page")).to_be_visible(timeout=60_000)
    await scenario.step(
        "Записи картотеки",
        page,
        screenshot_name="entities",
        label_en="Records",
        details=(
            "Раздел «Записи» — картотека: клиенты, сделки, лиды. Записи "
            "можно искать, фильтровать по типам и раскладывать по "
            "карточкам или таблице."
        ),
        details_en=(
            "The Records section is the card index: customers, deals, "
            "leads. Records can be searched, filtered by type and viewed "
            "as cards or a table."
        ),
    )

    await page.goto(f"{crm_ui.origin}/crm/graph", wait_until="domcontentloaded")
    await expect(page.locator("crm-graph-page")).to_be_visible(timeout=60_000)
    await scenario.step(
        "Граф связей",
        page,
        screenshot_name="graph",
        label_en="Relation graph",
        details=(
            "«Граф» рисует связи между записями: кто в какой компании "
            "работает, какая сделка к какому клиенту относится. Удобно "
            "увидеть картину целиком, а не по одной карточке."
        ),
        details_en=(
            "The Graph draws links between records: who works at which "
            "company, which deal belongs to which customer. A convenient "
            "way to see the whole picture instead of single cards."
        ),
    )

    await page.goto(f"{crm_ui.origin}/crm/suggests", wait_until="domcontentloaded")
    await expect(page.locator("crm-suggests-page")).to_be_visible(timeout=60_000)
    await scenario.step(
        "AI-предложения",
        page,
        screenshot_name="suggests",
        label_en="AI suggestions",
        details=(
            "«Предложения» — место, где платформа сама подсказывает, что "
            "нашла в заметках: новые контакты, встречи, задачи. Остаётся "
            "только подтвердить — и они станут записями."
        ),
        details_en=(
            "Suggestions is where the platform hints at what it found in "
            "your notes: new contacts, meetings, tasks. Just confirm — "
            "and they become records."
        ),
    )

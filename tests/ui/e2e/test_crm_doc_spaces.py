"""Документационные сценарии CRM: настройка пространства.

Маршруты пользователя: библиотека шаблонов пространств — что входит
в готовый шаблон и из каких типов записей он собран.
"""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.crm_activity_tasks_helpers import (
    crm_api_create_access_request,
    crm_api_create_entity,
    crm_api_ensure_namespace,
)
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


@pytest.mark.scenario(
    service="crm",
    tag="setup",
    doc_slug="access-requests",
    title="Заявки на доступ к записям",
    title_en="Access requests to records",
    description=(
        "**Для чего:** разбирать просьбы коллег открыть им закрытую "
        "запись — одобрить или отклонить в один клик.\n\n"
        "**Какие проблемы решает:** сотрудник видит ссылку на запись, "
        "но не имеет к ней доступа. Он отправляет заявку с пояснением, "
        "а владелец решает — дать доступ или нет. Всё без переписки "
        "в чатах.\n\n"
        "**Результат:** вы знаете, где лежат входящие заявки и как "
        "быстро их обработать."
    ),
    description_en=(
        "**Purpose:** handle colleagues' requests to open a restricted "
        "record — approve or reject in one click.\n\n"
        "**Problems solved:** an employee sees a link to a record but "
        "has no access to it. They send a request with a note, and the "
        "owner decides — grant access or not. No chat threads needed.\n\n"
        "**Result:** you know where incoming requests live and how to "
        "process them quickly."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_access_requests_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = f"e_{unique_id}"
    entity_name = f"Договор с «Металл-Сбыт» {unique_id[:6]}"

    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)
    entity_id = await crm_api_create_entity(
        crm_ui.origin,
        auth_token_system,
        entity_type="note",
        name=entity_name,
        namespace=namespace,
    )
    await crm_api_create_access_request(
        crm_ui.origin,
        auth_token_system,
        resource_id=entity_id,
        message=(
            "Здравствуйте! Нужен доступ к договору — готовлю акт сверки "
            "за этот квартал."
        ),
    )

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{crm_ui.origin}/crm/access-requests", wait_until="domcontentloaded"
    )
    requests_page = page.locator("crm-access-requests-page")
    await expect(requests_page).to_be_visible(timeout=60_000)
    pending_card = requests_page.locator(".request", has_text=entity_name)
    await expect(pending_card).to_be_visible(timeout=60_000)
    await scenario.step(
        "Входящие заявки",
        page,
        screenshot_name="access-requests-pending",
        label_en="Incoming requests",
        details=(
            "Раздел «Запросы доступа» показывает все заявки, которые "
            "ждут вашего решения. На карточке — кто просит, к какой "
            "записи и зачем. Клик по названию записи открывает её "
            "карточку, чтобы проверить, что внутри."
        ),
        details_en=(
            "The Access requests section lists every request waiting "
            "for your decision. Each card shows who asks, which record "
            "they need and why. Clicking the record name opens its "
            "card so you can check what is inside."
        ),
    )

    approve = pending_card.get_by_role(
        "button", name=re.compile("Одобрить|Approve")
    )
    await expect(approve).to_be_visible(timeout=30_000)
    await approve.click()
    await expect(pending_card).not_to_be_visible(timeout=60_000)
    approved_chip = requests_page.get_by_role(
        "button", name=re.compile("Одобренные|Approved")
    )
    await approved_chip.click()
    approved_card = requests_page.locator(".request", has_text=entity_name)
    await expect(approved_card).to_be_visible(timeout=60_000)
    await scenario.step(
        "Заявка обработана",
        page,
        screenshot_name="access-requests-approved",
        label_en="Request approved",
        details=(
            "«Одобрить» сразу открывает коллеге доступ к записи — "
            "заявка уходит из списка ожидания и появляется на вкладке "
            "«Одобренные» со статусом. «Отклонить» работает так же — "
            "заявка попадает в «Отклонённые».\n\n"
            "**Итог.** Заявки — это аккуратная очередь доступа: "
            "проситель пишет зачем ему запись, вы решаете в один клик."
        ),
        details_en=(
            "Approve immediately opens the record to the colleague — "
            "the request leaves the pending list and appears under the "
            "Approved tab with its status. Reject works the same way — "
            "the request lands in Rejected.\n\n"
            "**Summary.** Access requests are a tidy access queue: "
            "the requester explains why they need the record, you "
            "decide in one click."
        ),
    )


@pytest.mark.scenario(
    service="crm",
    tag="setup",
    doc_slug="namespace-integrations",
    title="Интеграции пространства: подключение amoCRM",
    title_en="Space integrations: connecting amoCRM",
    description=(
        "**Для чего:** связать пространство с внешней CRM — записи и "
        "поля подтянутся автоматически, а заметки смогут разбираться "
        "AI по расписанию.\n\n"
        "**Какие проблемы решает:** данные уже живут в amoCRM и "
        "заводить их руками долго. Интеграция забирает клиентов и "
        "сделки в пространство и держит их в актуальном состоянии.\n\n"
        "**Результат:** вы знаете, где подключить amoCRM и какие "
        "настройки синхронизации доступны."
    ),
    description_en=(
        "**Purpose:** link a space to an external CRM — records and "
        "fields sync automatically, and notes can be analysed by AI "
        "on a schedule.\n\n"
        "**Problems solved:** data already lives in amoCRM and typing "
        "it by hand is slow. The integration pulls customers and "
        "deals into the space and keeps them up to date.\n\n"
        "**Result:** you know where to connect amoCRM and which sync "
        "settings are available."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_namespace_integrations_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = f"e_{unique_id}"

    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{crm_ui.origin}/crm/namespaces/{namespace}/integrations",
        wait_until="domcontentloaded",
    )
    integrations_page = page.locator("crm-namespace-integrations-page")
    await expect(integrations_page).to_be_visible(timeout=60_000)
    panel = integrations_page.locator(".panel")
    await expect(panel).to_be_visible(timeout=60_000)
    await scenario.step(
        "Интеграции пространства",
        page,
        screenshot_name="integrations-panel",
        label_en="Space integrations",
        details=(
            "Страница «Пространство → Интеграции» показывает доступные "
            "подключения. Для amoCRM нужен только поддомен вашего "
            "аккаунта — остальное система сделает через OAuth: кнопка "
            "«Подключить» переведёт вас в amoCRM для подтверждения."
        ),
        details_en=(
            "The Space → Integrations page lists available "
            "connections. For amoCRM you only need your account "
            "subdomain — the rest goes through OAuth: the Connect "
            "button takes you to amoCRM to confirm."
        ),
    )

    subdomain_field = panel.locator("platform-field").first
    await expect(subdomain_field).to_be_visible(timeout=30_000)
    await subdomain_field.locator("input").fill("mycompany")
    await scenario.step(
        "Подключение по поддомену",
        page,
        screenshot_name="integrations-subdomain",
        label_en="Connect by subdomain",
        details=(
            "Введите поддомен amoCRM — например, `mycompany` из "
            "адреса `mycompany.amocrm.ru`. Ниже показан адрес возврата "
            "(OAuth callback) — он уже заполнен, его нужно указать в "
            "настройках интеграции на стороне amoCRM.\n\n"
            "**Итог.** После подключения записи и поля приезжают в "
            "пространство автоматически; расписание и AI-разбор "
            "заметок включаются здесь же переключателями."
        ),
        details_en=(
            "Enter your amoCRM subdomain — for example, `mycompany` "
            "from `mycompany.amocrm.ru`. Below is the return address "
            "(OAuth callback) — already filled in; copy it into the "
            "integration settings on the amoCRM side.\n\n"
            "**Summary.** Once connected, records and fields arrive "
            "in the space automatically; the sync schedule and AI "
            "note analysis are enabled by toggles on the same page."
        ),
    )

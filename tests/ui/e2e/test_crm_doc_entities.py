"""E2E-сценарии CRM: карточки записей и связи между ними."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.crm_activity_tasks_helpers import (
    crm_api_create_entity,
    crm_api_ensure_entity_type,
    crm_api_ensure_namespace,
    crm_api_ensure_relationship_type,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_activate_namespace_for_next_load
from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="crm",
    tag="entities",
    doc_slug="entity-detail-and-links",
    title="Карточка записи: поля и связи с другими записями",
    title_en="Record card: fields and links to other records",
    description=(
        "**Для чего:** держать всю информацию о клиенте в одном месте — "
        "поля записи и связи с другими записями.\n\n"
        "**Какие проблемы решает:** без связей карточка — просто строка "
        "в таблице. Связанные записи показывают окружение: контакт "
        "работает в компании, сделка относится к проекту.\n\n"
        "**Результат:** в карточке записи виден список связанных "
        "объектов, а новую связь можно добавить за полминуты."
    ),
    description_en=(
        "**Purpose:** keep everything about a customer in one place — "
        "record fields and links to other records.\n\n"
        "**Problems solved:** without links a card is just a table row. "
        "Linked records show the neighbourhood: a contact works at a "
        "company, a deal belongs to a project.\n\n"
        "**Result:** the record card lists linked objects, and a new "
        "link takes half a minute to add."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180, func_only=True)
async def test_crm_entity_detail_and_links_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = f"e_{unique_id}"
    org_name = f"ООО «Вектор» {unique_id[:6]}"
    contact_name = f"Мария Смирнова {unique_id[:6]}"

    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)
    for type_id, type_name in (
        ("organization", "Организация"),
        ("contact", "Контакт"),
    ):
        await crm_api_ensure_entity_type(
            crm_ui.origin,
            auth_token_system,
            type_id=type_id,
            name=type_name,
            namespace=namespace,
        )
    await crm_api_ensure_relationship_type(
        crm_ui.origin, auth_token_system, type_id="works_at", name="Работает в"
    )

    org_id = await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="organization", name=org_name, namespace=namespace,
    )
    await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="contact", name=contact_name, namespace=namespace,
    )

    await sync_e2e_activate_namespace_for_next_load(page, namespace)
    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{crm_ui.origin}/crm/entities/{org_id}", wait_until="domcontentloaded"
    )
    detail_page = page.locator("crm-entity-detail-page")
    await expect(detail_page).to_be_visible(timeout=60_000)
    await expect(
        detail_page.get_by_text(org_name, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Карточка записи",
        page,
        screenshot_name="entity-card",
        label_en="Record card",
        details=(
            "Карточка записи собирает всё в одном месте: имя, статус, "
            "поля по шаблону типа и блок «Связанные объекты» — кто и как "
            "связан с этой записью. Вкладка «Связи» показывает то же "
            "самое списком."
        ),
        details_en=(
            "The record card keeps everything in one place: name, "
            "status, template fields and the Linked objects block — "
            "who is linked to this record and how. The Relations tab "
            "shows the same as a list."
        ),
    )

    edit_button = detail_page.get_by_role(
        "button", name=re.compile("^Edit$|^Редактировать$")
    )
    await expect(edit_button).to_be_visible(timeout=30_000)
    await edit_button.click()

    add_button = detail_page.get_by_role(
        "button", name=re.compile("Добавить связь|Add relationship")
    )
    await expect(add_button).to_be_visible(timeout=30_000)
    await add_button.click()
    rel_form = detail_page.locator(".rel-add")
    await expect(rel_form).to_be_visible(timeout=30_000)

    rel_fields = rel_form.locator("platform-field")
    await ui_set_platform_field(rel_fields.nth(1), "works_at")
    target_input = rel_form.get_by_placeholder(re.compile("Find entity|Найти запись"))
    await target_input.fill(contact_name)
    result_button = rel_form.locator(".search-result", has_text=contact_name)
    await expect(result_button).to_be_visible(timeout=30_000)
    await result_button.click()
    await scenario.step(
        "Новая связь",
        page,
        screenshot_name="entity-link-form",
        label_en="New link form",
        details=(
            "Нажмите «Редактировать», затем «Добавить связь» — "
            "откроется форма: выберите тип связи (например, «Работает "
            "в») и начните вводить имя записи — подходящие карточки "
            "подставятся сами. Осталось нажать «Создать связь»."
        ),
        details_en=(
            "Click Edit, then Add relationship — the form opens: pick "
            "a link type (for example, Works at) and start typing a "
            "record name — matching cards are suggested. Then click "
            "Create relationship."
        ),
    )

    submit = rel_form.get_by_role(
        "button", name=re.compile("Создать связь|Create relationship")
    )
    await expect(submit).to_be_enabled(timeout=10_000)
    await submit.click()
    await expect(
        detail_page.get_by_text(contact_name, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Запись связана",
        page,
        screenshot_name="entity-linked-row",
        label_en="Record linked",
        details=(
            f"«{contact_name}» появилась в списке связанных объектов "
            "с типом связи и направлением. Клик по строке открывает "
            "карточку соседа — так удобно ходить по цепочке клиентов.\n\n"
            "**Итог.** Карточка записи — центр картотеки: поля, связи "
            "и быстрый переход к соседним записям."
        ),
        details_en=(
            f"{contact_name} now shows in the linked objects list with "
            "its link type and direction. Clicking a row opens the "
            "neighbour card — a handy way to walk the customer chain.\n\n"
            "**Summary.** The record card is the centre of the card "
            "index: fields, links and a quick hop to neighbours."
        ),
    )


@pytest.mark.scenario(
    service="crm",
    tag="entities",
    doc_slug="relationship-types",
    title="Свои типы связей",
    title_en="Custom link types",
    description=(
        "**Для чего:** описать связи компании своими словами — «Поставщик», "
        "«Партнёр», «Рекомендатель» — когда встроенных типов не хватает.\n\n"
        "**Какие проблемы решает:** без своего типа связь записывается "
        "как «прочее» и теряет смысл. Свой тип виден в карточке, на "
        "графе и в подписях связей.\n\n"
        "**Результат:** в каталоге связей появился ваш тип, и его можно "
        "выбирать при связывании записей."
    ),
    description_en=(
        "**Purpose:** describe company links in your own words — "
        "Supplier, Partner, Referrer — when built-in types are not "
        "enough.\n\n"
        "**Problems solved:** without a custom type a link is saved as "
        "miscellaneous and loses meaning. A custom type is visible on "
        "the card, the graph and link labels.\n\n"
        "**Result:** your type appears in the link catalogue, ready to "
        "pick when linking records."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_relationship_types_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    type_id = f"supplier_{unique_id[:8]}"
    type_name = f"Поставщик {unique_id[:6]}"

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{crm_ui.origin}/crm/relationship_types", wait_until="domcontentloaded"
    )
    types_page = page.locator("crm-relationship-types-page")
    await expect(types_page).to_be_visible(timeout=60_000)
    await expect(
        types_page.locator(".type-card").first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Каталог типов связей",
        page,
        screenshot_name="relationship-types-list",
        label_en="Link type catalogue",
        details=(
            "Раздел «Настройки → Типы связей» показывает все виды связей: "
            "встроенные (с пометкой «системный») и добавленные вами. У "
            "каждого типа — имя, идентификатор, направление и цвет для "
            "графа."
        ),
        details_en=(
            "The Settings → Link types section lists every link kind: "
            "built-in (marked system) and the ones you added. Each "
            "type has a name, an identifier, a direction and a graph "
            "colour."
        ),
    )

    add_button = types_page.get_by_role(
        "button", name=re.compile("Добавить тип|Add type")
    )
    await expect(add_button).to_be_visible(timeout=30_000)
    await add_button.click()
    form = types_page.locator(".form-grid")
    await expect(form).to_be_visible(timeout=30_000)
    form_fields = form.locator("platform-field")
    await ui_set_platform_field(form_fields.nth(0), type_id)
    await ui_set_platform_field(form_fields.nth(1), type_name)
    await ui_set_platform_field(
        form_fields.nth(2), "Компания поставляет нам товары и материалы"
    )
    await scenario.step(
        "Новый тип связи",
        page,
        screenshot_name="relationship-type-form",
        label_en="New link type",
        details=(
            "«Добавить тип» раскрывает форму: идентификатор (латиницей, "
            "например `supplier`), понятное имя, описание, обратный тип "
            "(«поставляет» ↔ «покупает у»), цвет и направление. Вес "
            "влияет на то, насколько важной связь выглядит на графе."
        ),
        details_en=(
            "Add type unfolds a form: identifier (latin, e.g. "
            "`supplier`), a friendly name, a description, the inverse "
            "type (supplies ↔ buys from), a colour and direction. "
            "Weight affects how important the link looks on the graph."
        ),
    )

    submit = types_page.get_by_role(
        "button", name=re.compile("Создать|Create")
    )
    await expect(submit).to_be_enabled(timeout=10_000)
    await submit.click()
    new_card = types_page.locator(".type-card", has_text=type_name)
    await expect(new_card).to_be_visible(timeout=60_000)
    await new_card.scroll_into_view_if_needed()
    await scenario.step(
        "Тип в каталоге",
        page,
        screenshot_name="relationship-type-created",
        label_en="Type created",
        details=(
            f"«{type_name}» появился в каталоге рядом со встроенными "
            "типами — теперь его можно выбирать при добавлении связи в "
            "карточке записи.\n\n"
            "**Итог.** Свои типы связей делают картотеку точнее: "
            "каждая связь читается словами вашего бизнеса."
        ),
        details_en=(
            f"{type_name} now sits in the catalogue next to built-in "
            "types — ready to pick when adding a link on a record "
            "card.\n\n"
            "**Summary.** Custom link types make the card index "
            "sharper: every link reads in your business's own words."
        ),
    )

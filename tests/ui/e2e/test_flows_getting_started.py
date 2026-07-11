"""UI E2E сценарии Flows: первые шаги (главная и создание первого агента).

Сквозной пример «Зелёный сад» — см. docs/scenarios/flows/CATALOG.md.
"""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_chat_echo_payload,
    flows_chat_send_message,
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_set_platform_field,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="getting-started",
    doc_slug="flows-home-tour",
    title="Знакомство с Flows: главная и каталог агентов",
    description=(
        "**Для чего:** эта инструкция поможет освоиться на главной странице Flows "
        "и научиться находить нужного агента и открывать с ним чат.\n\n"
        "**Какие проблемы решает:** новый пользователь часто не понимает, где список "
        "агентов, как открыть диалог или редактор и куда нажимать в первую очередь.\n\n"
        "**Результат:** вы найдёте «Помощника Зелёного сада» в каталоге и откроете с ним "
        "рабочий чат."
    ),
    title_en="Getting to know Flows: home and agent catalog",
    description_en=(
        "**What for:** this guide helps you get comfortable on the Flows home page "
        "and learn how to find an agent and open a chat with it.\n\n"
        "**Problems it solves:** new users often can't tell where the agent list is, "
        "how to open a dialog or the editor, and what to click first.\n\n"
        "**Result:** you will find the Green Garden Assistant in the catalog and open a "
        "working chat with it."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_home_tour(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    flow_id = flows_doc_flow_id("home_tour", unique_id)
    payload = flows_chat_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME)
    await flows_api_create_flow(flows_ui.origin, auth_token_system, payload)

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте главную Flows",
        page,
        screenshot_name="flows-home-opened",
        label_en="Open the Flows home page",
        details=(
            "Перейдите в сервис Flows. В центре — приветственный блок и быстрые "
            "действия, а слева каталог ваших агентов. Так вы сразу видите, с чего "
            "начать работу."
        ),
        details_en=(
            "Open the Flows service. In the center you see the welcome block and quick "
            "actions, and on the left the catalog of your agents. This shows you where "
            "to start right away."
        ),
    )

    hero_actions = page.locator("flows-home-page .hero-actions").first
    await expect(hero_actions).to_be_visible(timeout=15_000)
    download_link = hero_actions.locator("a.hero-download-link").first
    await expect(download_link).to_be_visible(timeout=15_000)
    operator_button = hero_actions.locator("platform-button").filter(
        has_text=re.compile(r"Оператор|Operator|HITL")
    ).first
    await expect(operator_button).to_be_visible(timeout=15_000)
    await scenario.step(
        "Посмотрите быстрые действия и ссылку на LinnexAgent",
        page,
        screenshot_name="hero-quick-actions",
        label_en="Review quick actions and the LinnexAgent download link",
        details=(
            "В блоке быстрых действий есть кнопки «Сессии», «Оператор / HITL» и ссылка "
            "«Скачать LinnexAgent» для desktop-клиента. Отсюда можно перейти к задачам "
            "операторов или скачать приложение для pairing и Platform MCP."
        ),
        details_en=(
            "The quick actions block includes Sessions, Operator / HITL, and a "
            "Download LinnexAgent link for the desktop client. From here you can open "
            "operator tasks or download the app for pairing and Platform MCP."
        ),
    )

    sessions_button = hero_actions.locator("platform-button").filter(
        has_text=re.compile(r"Сессии|Sessions")
    ).first
    await sessions_button.locator("button").first.click()
    sessions_modal = page.locator("flows-sessions-modal").first
    await expect(sessions_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте недавние сессии",
        page,
        screenshot_name="recent-sessions-modal",
        label_en="Open recent sessions",
        details=(
            "Кнопка «Сессии» открывает список недавних диалогов с агентами. Здесь можно "
            "продолжить разговор или посмотреть, какие агенты недавно запускались."
        ),
        details_en=(
            "The Sessions button opens a list of recent agent conversations. Here you "
            "can resume a dialog or see which agents ran recently."
        ),
    )
    await page.keyboard.press("Escape")
    await expect(sessions_modal).to_be_hidden(timeout=15_000)

    catalog = page.locator("flows-catalog-list").first
    await expect(catalog).to_be_visible(timeout=30_000)
    search = catalog.locator("platform-modal-search-field").first
    if await search.count() > 0:
        await search.evaluate(
            """
            (el, value) => {
                el.value = value;
                if (typeof el.requestUpdate === 'function') el.requestUpdate();
                el.dispatchEvent(new CustomEvent('change', { detail: { value }, bubbles: true, composed: true }));
            }
            """,
            GREEN_GARDEN_AGENT_NAME,
        )
    card = catalog.locator("flow-card").filter(has_text=GREEN_GARDEN_AGENT_NAME).first
    await expect(card).to_be_visible(timeout=30_000)
    await card.scroll_into_view_if_needed()
    await scenario.step(
        "Найдите нужного агента в каталоге",
        page,
        screenshot_name="agent-found-in-catalog",
        label_en="Find the agent in the catalog",
        details=(
            "Введите часть названия в поиск каталога. Список сузится до подходящих "
            "агентов — так удобно находить нужного помощника, когда их много. "
            "Появится карточка «Помощника Зелёного сада»."
        ),
        details_en=(
            "Type part of the name into the catalog search. The list narrows to matching "
            "agents, which is handy when you have many. The Green Garden Assistant card "
            "appears."
        ),
    )

    await card.hover()
    editor_button = card.locator("[data-action='edit-flow']").first
    chat_button = card.locator("[data-action='open-chat']").first
    await expect(editor_button).to_be_visible(timeout=15_000)
    await expect(chat_button).to_be_visible(timeout=15_000)
    await scenario.step(
        "Раскройте карточку агента",
        page,
        screenshot_name="agent-card-actions",
        label_en="Reveal agent card actions",
        details=(
            "Наведите курсор на карточку «Помощника Зелёного сада». Появятся кнопки "
            "«Чат» и «Редактор» — чат для проверки агента, редактор для настройки графа."
        ),
        details_en=(
            "Hover over the Green Garden Assistant card. Chat and Editor buttons appear — "
            "chat to try the agent, editor to configure the graph."
        ),
    )
    await chat_button.click(force=True)
    await expect(page.locator("chat-page platform-chat")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте чат агента",
        page,
        screenshot_name="agent-chat-opened",
        label_en="Open the agent chat",
        details=(
            "Нажмите значок чата на карточке агента. Откроется диалог, в котором можно "
            "общаться с помощником как обычный покупатель. Это главный способ проверить "
            "агента в деле."
        ),
        details_en=(
            "Click the chat icon on the agent card. A dialog opens where you can talk to "
            "the assistant like a regular customer. This is the main way to try the agent "
            "in action."
        ),
    )

    await flows_chat_send_message(page, "Здравствуйте! Подскажите про доставку.")
    reply = page.get_by_text(re.compile(r"chat-ok:"), exact=False).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Проверьте ответ агента",
        page,
        screenshot_name="agent-answered",
        label_en="Check the agent reply",
        details=(
            "**Демонстрация результата.** Отправьте вопрос и дождитесь ответа в ленте "
            "чата — видимый ответ подтверждает, что агент найден и работает.\n\n"
            "**Итог.** Теперь вы умеете ориентироваться на главной Flows, находить "
            "быстрые действия и сессии, находить агента в каталоге и открывать с ним "
            "рабочий чат."
        ),
        details_en=(
            "**Result demonstration.** Send a question and wait for the reply in the chat "
            "feed; a visible answer confirms the agent is found and working.\n\n"
            "**Summary.** You can now navigate the Flows home, use quick actions and "
            "sessions, find an agent in the catalog, and open a working chat with it."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="getting-started",
    doc_slug="create-first-agent",
    title="Создаём первого агента из шаблона",
    description=(
        "**Для чего:** эта инструкция поможет создать собственного агента, не собирая "
        "граф с нуля.\n\n"
        "**Какие проблемы решает:** новичку непонятно, с какого шаблона начать и какие "
        "поля нужно заполнить при создании.\n\n"
        "**Результат:** «Помощник Зелёного сада» создан и открыт в редакторе с готовыми "
        "нодами."
    ),
    title_en="Create your first agent from a template",
    description_en=(
        "**What for:** this guide helps you create your own agent without building a "
        "graph from scratch.\n\n"
        "**Problems it solves:** beginners aren't sure which template to start from and "
        "which fields to fill in when creating an agent.\n\n"
        "**Result:** the Green Garden Assistant is created and opened in the editor with "
        "ready-made nodes."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_create_first_agent(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте каталог агентов",
        page,
        screenshot_name="catalog-before-create",
        label_en="Open the agent catalog",
        details=(
            "На главной Flows слева находится каталог агентов. Здесь можно не только "
            "искать готовых помощников, но и создать нового."
        ),
        details_en=(
            "On the Flows home, the agent catalog is on the left. Here you can not only "
            "search existing assistants but also create a new one."
        ),
    )

    create_button = page.locator("flows-catalog-list [data-action='create-flow']").first
    await expect(create_button).to_be_visible(timeout=30_000)
    await create_button.click()
    modal = page.locator("flows-flow-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Выберите шаблон агента",
        page,
        screenshot_name="create-wizard-templates",
        label_en="Choose an agent template",
        details=(
            "Откроется мастер создания. Выберите шаблон обычного агента — он уже содержит "
            "ноду ответа, поэтому агент сразу сможет отвечать покупателям."
        ),
        details_en=(
            "The creation wizard opens. Pick the plain agent template — it already "
            "contains an answer node, so the agent can reply to customers immediately."
        ),
    )
    preset = modal.locator("platform-picker-card[value='react']").first
    await expect(preset).to_be_visible(timeout=15_000)
    await preset.click()

    fields = modal.locator("platform-field")
    await expect(fields.first).to_be_visible(timeout=15_000)
    # id / name / description — порядок полей в шаге ввода
    flow_id = flows_doc_flow_id("green_garden", unique_id)
    await flows_set_platform_field(fields.nth(0), flow_id)
    if await fields.count() > 1:
        await flows_set_platform_field(fields.nth(1), GREEN_GARDEN_AGENT_NAME)
    if await fields.count() > 2:
        await flows_set_platform_field(
            fields.nth(2), "Помощник интернет-магазина садовых товаров"
        )
    await scenario.step(
        "Заполните название и описание",
        page,
        screenshot_name="create-wizard-fields",
        label_en="Fill in name and description",
        details=(
            "Укажите идентификатор, название «Помощник Зелёного сада» и короткое "
            "описание. Идентификатор нужен системе, а название и описание увидят коллеги "
            "в каталоге."
        ),
        details_en=(
            "Enter an identifier, the name Green Garden Assistant, and a short "
            "description. The identifier is for the system, while the name and "
            "description are what colleagues see in the catalog."
        ),
    )

    await flows_click_platform_button(modal, "Создать", "Create", "Готово", "Done")
    await expect(page.locator("flows-flow-canvas svg.canvas-host")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-flow-canvas g.node")).to_have_count(1, timeout=30_000)
    await scenario.step(
        "Проверьте нового агента в редакторе",
        page,
        screenshot_name="new-agent-in-editor",
        label_en="Check the new agent in the editor",
        details=(
            "**Демонстрация результата.** После создания вы сразу попадаете в редактор, а "
            "на канве уже есть стартовая нода ответа — значит агент создан и готов к "
            "настройке.\n\n"
            "**Итог.** Теперь вы умеете создавать агента из шаблона и понимаете, какие "
            "поля заполнять."
        ),
        details_en=(
            "**Result demonstration.** After creation you land in the editor and the "
            "canvas already has a starter answer node, which means the agent is created "
            "and ready to configure.\n\n"
            "**Summary.** You can now create an agent from a template and know which "
            "fields to fill in."
        ),
    )

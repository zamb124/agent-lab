"""UI E2E сценарии Flows: Agent Skills (библиотека, attach, чат, duplicate)."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_chat_send_message,
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_e2e_attach_skill_to_llm_node,
    flows_e2e_expect_skill_load_chip,
    flows_e2e_open_skill_library,
    flows_e2e_save_skill_editor,
    flows_e2e_seed_agent_skill,
    flows_e2e_set_llm_output_mode,
    flows_e2e_set_skill_body,
    flows_llm_payload,
    flows_open_chat_page,
    flows_open_editor,
    flows_publish_editor,
    flows_seed_mock_llm,
    flows_set_platform_field,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_RETURN_SKILL_BODY = (
    "# Возврат заказа\n\n"
    "1. Уточните номер заказа у покупателя «Зелёного сада».\n"
    "2. Проверьте срок возврата по политике магазина.\n"
    "3. Если нужна арифметика суммы — вызовите calculator.\n"
)


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="manage-agent-skills",
    title="Создаём Skill «Возврат заказа»",
    description=(
        "**Для чего:** эта инструкция поможет завести процедуру (Skill) для помощника "
        "магазина — пошаговый сценарий возврата заказа.\n\n"
        "**Какие проблемы решает:** непонятно, где библиотека Skills и чем Skill "
        "отличается от инструмента и от ветки графа.\n\n"
        "**Результат:** Skill «Возврат заказа» есть в библиотеке с именем, описанием "
        "и текстом процедуры."
    ),
    title_en="Create the Order return Skill",
    description_en=(
        "**What for:** this guide helps you create a procedure (Skill) for the store "
        "assistant — a step-by-step order return scenario.\n\n"
        "**Problems it solves:** it is unclear where the Skills library is and how a "
        "Skill differs from a tool or a graph branch.\n\n"
        "**Result:** the Order return Skill is in the library with name, description, "
        "and procedure text."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_manage_agent_skills(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    secrets_service,
    taskiq_worker,
    flows_service,
) -> None:
    _ = secrets_service, taskiq_worker, flows_service
    skill_id = f"order-return-{unique_id[:8]}".lower().replace("_", "-")
    skill_name = skill_id
    page = ui_page_system

    await flows_e2e_open_skill_library(page, flows_ui)
    await scenario.step(
        "Откройте библиотеку Skills",
        page,
        screenshot_name="skills-library-opened",
        label_en="Open the Skills library",
        details=(
            "В Flows откройте раздел Skills. Здесь хранятся процедуры, которые агент "
            "может подключать по необходимости — это не ветка графа и не обычный "
            "инструмент из списка Tools."
        ),
        details_en=(
            "In Flows open the Skills section. Procedures live here that the agent can "
            "load when needed — not a graph branch and not a standing Tools chip."
        ),
    )

    create_btn = page.locator("flows-agent-skills-page page-header platform-button").filter(
        has_text=re.compile(r"Создать skill|Create skill", re.I)
    ).first
    await expect(create_btn).to_be_visible(timeout=30_000)
    await create_btn.locator("button").first.click()
    modal = page.locator("flows-agent-skill-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    fields = modal.locator("platform-field")
    await flows_set_platform_field(fields.nth(0), skill_id)
    await flows_set_platform_field(fields.nth(1), skill_name)
    await flows_set_platform_field(
        fields.nth(2),
        "Процедура возврата заказа для покупателей Зелёного сада.",
    )
    await scenario.step(
        "Заполните идентификатор, имя и описание",
        page,
        screenshot_name="skill-create-fields",
        label_en="Fill id, name, and description",
        details=(
            "В форме создания укажите короткий идентификатор латиницей (например "
            "order-return), то же значение в поле имени и описание про возврат для "
            "«Зелёного сада». Так Skill легко найти в библиотеке."
        ),
        details_en=(
            "In the create form set a short latin id (for example order-return), the same "
            "value as the name, and a description about Green Garden returns so the Skill "
            "is easy to find."
        ),
    )

    await flows_click_platform_button(modal, "Создать", "Create")
    await expect(modal).to_be_hidden(timeout=30_000)
    editor = page.locator("flows-agent-skill-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    await expect(editor).to_contain_text(skill_id, timeout=15_000)
    await scenario.step(
        "Создайте Skill и откройте редактор",
        page,
        screenshot_name="skill-editor-opened",
        label_en="Create the Skill and open the editor",
        details=(
            "Нажмите «Создать». Откроется редактор процедуры: здесь пишут шаги, которые "
            "агент прочитает после активации Skill."
        ),
        details_en=(
            "Click Create. The procedure editor opens — write the steps the agent reads "
            "after the Skill is loaded."
        ),
    )

    await flows_e2e_set_skill_body(page, _RETURN_SKILL_BODY)
    await flows_e2e_save_skill_editor(page)
    await scenario.step(
        "Напишите процедуру и сохраните",
        page,
        screenshot_name="skill-body-saved",
        label_en="Write the procedure and save",
        details=(
            "Опишите шаги возврата для «Зелёного сада» и сохраните. Текст процедуры — "
            "инструкция для агента, а не код графа."
        ),
        details_en=(
            "Describe the Green Garden return steps and save. Procedure text is guidance "
            "for the agent, not graph code."
        ),
    )

    skill_row = page.locator("flows-agent-skills-list").get_by_text(skill_id, exact=False).first
    await expect(skill_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Убедитесь, что Skill в списке библиотеки",
        page,
        screenshot_name="skill-in-library",
        label_en="Confirm the Skill is in the library list",
        details=(
            "**Демонстрация результата.** В списке Skills видна карточка процедуры "
            "возврата — её можно подключать к агентам.\n\n"
            "**Итог.** Вы умеете открывать библиотеку Skills, создавать процедуру и "
            "сохранять её текст."
        ),
        details_en=(
            "**Result demonstration.** The Skills list shows the return procedure card — "
            "you can attach it to agents.\n\n"
            "**Summary.** You can open the Skills library, create a procedure, and save "
            "its text."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="attach-skills-to-agent",
    title="Подключаем Skill к агенту",
    description=(
        "**Для чего:** эта инструкция покажет, как привязать Skill к ноде ответа в "
        "режиме «Инструменты».\n\n"
        "**Какие проблемы решает:** Skill есть в библиотеке, но агент его не видит — "
        "нужно явное подключение на ноде.\n\n"
        "**Результат:** у «Помощника Зелёного сада» чип Skill в режиме Инструменты; "
        "в Структурированном секция Skills скрыта."
    ),
    title_en="Attach a Skill to the agent",
    description_en=(
        "**What for:** this guide shows how to attach a Skill to the answer node in "
        "Tools mode.\n\n"
        "**Problems it solves:** the Skill exists in the library but the agent does not "
        "see it — you must attach it on the node.\n\n"
        "**Result:** the Green Garden Assistant has a Skill chip in Tools mode; in "
        "Structured mode the Skills section is hidden."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_attach_skills_to_agent(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
    flows_service,
) -> None:
    _ = secrets_service, taskiq_worker, flows_service
    skill_id = f"attach-return-{unique_id[:8]}".lower().replace("_", "-")
    skill_name = skill_id
    await flows_e2e_seed_agent_skill(
        flows_ui.origin,
        auth_token_system,
        agent_skill_id=skill_id,
        name=skill_id,
        description="Return procedure for Green Garden customers",
        body_markdown=_RETURN_SKILL_BODY,
    )
    flow_id = flows_doc_flow_id("attach_skill", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Помогай с возвратами по процедуре магазина.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id, layout="agent")
    studio = page.locator("flows-agent-focus-studio").first
    await expect(studio).to_be_visible(timeout=8_000)
    skills_tab = studio.locator("platform-segmented-control").get_by_role(
        "button", name=re.compile(r"Skills|Tools|Инструмент", re.I)
    ).first
    await expect(skills_tab).to_be_visible(timeout=15_000)
    await skills_tab.click()
    await flows_e2e_set_llm_output_mode(page, "tools")
    await scenario.step(
        "Откройте агента в режиме Инструменты",
        page,
        screenshot_name="tools-mode-for-skills",
        label_en="Open the agent in Tools mode",
        details=(
            "Откройте студию агента, секцию Skills и tools, и выберите режим "
            "«Инструменты». Секция Skills видна только здесь: при «Структурированный» "
            "её нет. Meta-tools загрузки Skill появляются сами после attach и не "
            "показываются как обычные Tools-чипы."
        ),
        details_en=(
            "Open agent Studio, the Skills and tools section, and choose Tools mode. "
            "The Skills section appears only here — not in Structured. Skill load "
            "meta-tools appear after attach and are not standing Tools chips."
        ),
    )

    await flows_e2e_attach_skill_to_llm_node(page, skill_name)
    skill_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(re.escape(skill_name), re.I)
    ).first
    await expect(skill_chip).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте Skill из библиотеки",
        page,
        screenshot_name="skill-chip-attached",
        label_en="Add the Skill from the library",
        details=(
            "Нажмите «Добавить skill», выберите Skill возврата и подтвердите. На ноде "
            "появится чип Skill."
        ),
        details_en=(
            "Click Add skill, pick the return Skill, and confirm. A Skill chip appears "
            "on the node."
        ),
    )

    await skill_chip.click()
    edit_modal = page.locator("flows-agent-skill-edit-modal").first
    await expect(edit_modal).to_be_visible(timeout=30_000)
    await expect(edit_modal).to_contain_text(skill_name, timeout=15_000)
    await scenario.step(
        "Откройте Skill с чипа",
        page,
        screenshot_name="skill-chip-edit-modal",
        label_en="Open the Skill from the chip",
        details=(
            "Клик по чипу открывает редактирование процедуры — можно поправить шаги, "
            "не уходя в библиотеку."
        ),
        details_en=(
            "Clicking the chip opens the procedure editor so you can fix steps without "
            "leaving the node."
        ),
    )
    await page.keyboard.press("Escape")
    await expect(edit_modal).to_be_hidden(timeout=15_000)

    await skills_tab.click()
    await flows_e2e_set_llm_output_mode(page, "structured")
    skills_heading = page.locator("flows-llm-node-editor").get_by_text(
        re.compile(r"^Skills$|^Навыки$", re.I)
    )
    await expect(skills_heading).to_have_count(0, timeout=15_000)
    await scenario.step(
        "Переключите Структурированный — секция Skills скрыта",
        page,
        screenshot_name="structured-hides-skills",
        label_en="Switch to Structured — Skills section hidden",
        details=(
            "В режиме «Структурированный» секция Skills не показывается: агент отдаёт "
            "JSON, а не подгружает процедуры. Attach в конфиге сохраняется."
        ),
        details_en=(
            "In Structured mode the Skills section is hidden: the agent returns JSON, "
            "not loaded procedures. The attach stays in the config."
        ),
    )

    await flows_e2e_set_llm_output_mode(page, "tools")
    await skills_tab.click()
    await expect(skill_chip).to_be_visible(timeout=30_000)
    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    attached = persisted["nodes"]["agent"].get("agent_skills") or []
    assert skill_id in attached, f"skill not persisted: {attached!r}"
    await scenario.step(
        "Вернитесь в Инструменты и опубликуйте",
        page,
        screenshot_name="skill-chip-tools-demo",
        label_en="Return to Tools and publish",
        details=(
            "**Демонстрация результата.** Снова режим «Инструменты» — чип Skill на месте; "
            "после публикации attach сохранён.\n\n"
            "**Итог.** Вы умеете подключать Skill к агенту в режиме Инструменты и "
            "понимаете, что в Структурированном секция скрыта."
        ),
        details_en=(
            "**Result demonstration.** Back in Tools mode the Skill chip remains; after "
            "publish the attach is saved.\n\n"
            "**Summary.** You can attach a Skill in Tools mode and know Structured hides "
            "the Skills section."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    doc_slug="skills-unlock-in-chat",
    title="Skill активируется в чате",
    description=(
        "**Для чего:** эта инструкция покажет, как в чате видно, что агент загрузил "
        "Skill и использовал его инструменты.\n\n"
        "**Какие проблемы решает:** непонятно, сработала ли процедура и откуда взялся "
        "калькулятор в ответе.\n\n"
        "**Результат:** в чате виден чип загрузки Skill и ответ с расчётом."
    ),
    title_en="A Skill unlocks in chat",
    description_en=(
        "**What for:** this guide shows how chat reveals that the agent loaded a Skill "
        "and used its tools.\n\n"
        "**Problems it solves:** it is unclear whether the procedure ran and where the "
        "calculator in the reply came from.\n\n"
        "**Result:** the chat shows a Skill load chip and a reply with the calculation."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_skills_unlock_in_chat(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
    flows_service,
) -> None:
    _ = secrets_service, taskiq_worker, flows_service
    skill_id = f"chat-return-{unique_id[:8]}".lower().replace("_", "-")
    skill_name = skill_id
    await flows_e2e_seed_agent_skill(
        flows_ui.origin,
        auth_token_system,
        agent_skill_id=skill_id,
        name=skill_id,
        description="Return with calculator",
        body_markdown=_RETURN_SKILL_BODY,
        tool_refs=[
            {
                "tool_id": "calculator",
                "description": "Арифметика суммы возврата",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                    },
                    "required": ["expression"],
                },
            }
        ],
    )
    flow_id = flows_doc_flow_id("skill_chat", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt=(
                "Ты помощник «Зелёного сада». Для возврата загрузи Skill и посчитай "
                "сумму через calculator."
            ),
            agent_skills=[skill_id],
        ),
    )

    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, flow_id)
    chat = page.locator("flows-chat-page platform-flow-ui").first
    await expect(chat).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте чат с агентом",
        page,
        screenshot_name="skill-chat-opened",
        label_en="Open the agent chat",
        details=(
            "Откройте чат «Помощника Зелёного сада». Skill уже привязан к агенту — "
            "покупатель просто пишет вопрос о возврате."
        ),
        details_en=(
            "Open the Green Garden Assistant chat. The Skill is already attached — the "
            "customer just asks about a return."
        ),
    )

    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": "load_agent_skill",
                "args": {"agent_skill_id": skill_id},
            },
            {
                "type": "tool_call",
                "tool": "calculator",
                "args": {"expression": "1500-300"},
            },
            {
                "type": "text",
                "content": "К возврату по заказу: 1200 ₽. Skill «Возврат заказа» применён.",
            },
        ]
    )
    await scenario.step(
        "Подготовьте проверку ответа",
        page,
        screenshot_name="skill-chat-ready",
        label_en="Prepare the reply check",
        details=(
            "Агент сначала загрузит процедуру, затем посчитает сумму. Чип активации "
            "Skill в чате можно скрыть в настройках чата (отдельная инструкция)."
        ),
        details_en=(
            "The agent loads the procedure first, then calculates. Skill load chips can "
            "be hidden in chat settings (a separate guide)."
        ),
    )

    await flows_chat_send_message(page, "Оформите возврат: 1500 минус скидка 300")
    await flows_e2e_expect_skill_load_chip(page, skill_name)
    await scenario.step(
        "Отправьте вопрос и увидьте чип Skill",
        page,
        screenshot_name="skill-load-chip",
        label_en="Send a question and see the Skill chip",
        details=(
            "Напишите про возврат с суммой. В ленте появится чип, что агент загрузил "
            "Skill «Возврат заказа»."
        ),
        details_en=(
            "Ask about a return with amounts. The feed shows a chip that the agent "
            "loaded the Order return Skill."
        ),
    )

    reply = chat.get_by_text(re.compile(r"1200"), exact=False).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Проверьте ответ с результатом расчёта",
        page,
        screenshot_name="skill-chat-reply",
        label_en="Check the reply with the calculation",
        details=(
            "**Демонстрация результата.** В ответе видна сумма после calculator — "
            "процедура и инструмент Skill сработали в одном диалоге.\n\n"
            "**Итог.** Вы видите активацию Skill в чате и результат unlocked-инструмента."
        ),
        details_en=(
            "**Result demonstration.** The reply shows the amount after calculator — "
            "the procedure and unlocked tool ran in one dialog.\n\n"
            "**Summary.** You can see Skill activation in chat and the unlocked tool "
            "result."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="duplicate-and-edit-skill",
    title="Дублируем и правим Skill",
    description=(
        "**Для чего:** эта инструкция поможет скопировать Skill и подправить процедуру "
        "под другой кейс магазина.\n\n"
        "**Какие проблемы решает:** похожий сценарий уже есть, но менять оригинал "
        "нельзя — нужна копия с новым идентификатором.\n\n"
        "**Результат:** в библиотеке есть копия Skill с обновлённым текстом."
    ),
    title_en="Duplicate and edit a Skill",
    description_en=(
        "**What for:** this guide helps you copy a Skill and adjust the procedure for "
        "another store case.\n\n"
        "**Problems it solves:** a similar scenario already exists, but you must not "
        "change the original — you need a copy with a new id.\n\n"
        "**Result:** the library has a Skill copy with updated text."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_duplicate_and_edit_skill(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
    flows_service,
) -> None:
    _ = secrets_service, taskiq_worker, flows_service
    source_id = f"src-return-{unique_id[:8]}".lower().replace("_", "-")
    copy_id = f"copy-return-{unique_id[:8]}".lower().replace("_", "-")
    source_name = source_id
    copy_name = copy_id
    await flows_e2e_seed_agent_skill(
        flows_ui.origin,
        auth_token_system,
        agent_skill_id=source_id,
        name=source_id,
        description="Base return procedure",
        body_markdown=_RETURN_SKILL_BODY,
    )

    page = ui_page_system
    await flows_e2e_open_skill_library(page, flows_ui)
    row = page.locator("flows-agent-skills-list").get_by_text(source_name, exact=False).first
    await expect(row).to_be_visible(timeout=30_000)
    await row.click()
    editor = page.locator("flows-agent-skill-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте исходный Skill",
        page,
        screenshot_name="source-skill-opened",
        label_en="Open the source Skill",
        details=(
            "В библиотеке выберите «Возврат заказа». Справа откроется редактор — отсюда "
            "можно сделать копию, не меняя оригинал."
        ),
        details_en=(
            "In the library pick Order return. The editor opens on the right — from here "
            "you can duplicate without changing the original."
        ),
    )

    await flows_click_platform_button(editor, "Скопировать", "Duplicate", "Дублировать")
    panel = editor.locator('[data-testid="agent-skill-duplicate-panel"]').first
    await expect(panel).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте форму дублирования",
        page,
        screenshot_name="duplicate-panel-opened",
        label_en="Open the duplicate form",
        details=(
            "Нажмите «Дублировать». Появятся поля нового идентификатора и имени копии."
        ),
        details_en=(
            "Click Duplicate. Fields for the new id and copy name appear."
        ),
    )

    dup_fields = panel.locator("platform-field")
    await flows_set_platform_field(dup_fields.nth(0), copy_id)
    await flows_set_platform_field(dup_fields.nth(1), copy_name)
    await flows_click_platform_button(panel, "Создать копию", "Create copy", "Дублировать", "Duplicate")
    await expect(editor).to_contain_text(copy_id, timeout=30_000)
    await scenario.step(
        "Задайте id и имя копии",
        page,
        screenshot_name="duplicate-created",
        label_en="Set the copy id and name",
        details=(
            "Укажите новый идентификатор и имя вроде «Возврат заказа (лето)» и "
            "подтвердите. Редактор переключится на копию."
        ),
        details_en=(
            "Enter a new id and a name such as Order return (summer) and confirm. The "
            "editor switches to the copy."
        ),
    )

    summer_body = _RETURN_SKILL_BODY + "\n\nУчитывайте летнюю акцию на доставку.\n"
    await flows_e2e_set_skill_body(page, summer_body)
    await flows_e2e_save_skill_editor(page)
    copy_row = page.locator("flows-agent-skills-list").get_by_text(copy_name, exact=False).first
    await expect(copy_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Отредактируйте копию и найдите её в списке",
        page,
        screenshot_name="duplicate-edited-in-list",
        label_en="Edit the copy and find it in the list",
        details=(
            "**Демонстрация результата.** Допишите шаги под летний кейс, сохраните — "
            "в библиотеке видна отдельная карточка копии.\n\n"
            "**Итог.** Вы умеете дублировать Skill и править копию без изменения "
            "оригинала."
        ),
        details_en=(
            "**Result demonstration.** Extend the steps for the summer case, save — the "
            "library shows a separate copy card.\n\n"
            "**Summary.** You can duplicate a Skill and edit the copy without changing "
            "the original."
        ),
    )

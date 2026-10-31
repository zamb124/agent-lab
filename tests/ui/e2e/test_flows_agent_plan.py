"""UI E2E сценарии Flows: Agent Plan (Skill и ручные инструменты) → checklist в чате."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_chat_send_message,
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_e2e_agent_plan_mock_writes,
    flows_e2e_attach_skill_to_llm_node,
    flows_e2e_ensure_platform_skills_seed,
    flows_e2e_expect_agent_plan_block,
    flows_e2e_open_studio_skills_tools,
    flows_e2e_switch_editor_layout,
    flows_llm_add_named_tool_from_library,
    flows_open_chat_page,
    flows_publish_editor,
    flows_seed_mock_llm,
    flows_set_platform_field,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_PLANNING_SKILL_ID = "agent-planning"
_STEP_FIND = "Найти заказ покупателя"
_STEP_DELIVERY = "Проверить статус доставки"
_STEP_CONFIRM = "Подтвердить состав"
_FINAL_REPLY = "Заказ найден: доставка завтра, состав подтверждён."
_USER_PROMPT = (
    "Проверьте заказ 4521: найдите его в системе, проверьте доставку "
    "и подтвердите состав — покажите шаги по ходу работы."
)


async def _create_agent_wizard_steps(
    scenario: ScenarioRecorder,
    page: Page,
    flows_ui: AppUI,
    *,
    flow_id: str,
) -> None:
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    create_button = page.locator("flows-catalog-list [data-action='create-flow']").first
    await expect(create_button).to_be_visible(timeout=30_000)
    await create_button.click()
    modal = page.locator("flows-flow-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    preset = modal.locator("platform-picker-card[value='react']").first
    await expect(preset).to_be_visible(timeout=15_000)
    await preset.click()
    fields = modal.locator("platform-field")
    await expect(fields.first).to_be_visible(timeout=15_000)
    await flows_set_platform_field(fields.nth(0), flow_id)
    if await fields.count() > 1:
        await flows_set_platform_field(fields.nth(1), GREEN_GARDEN_AGENT_NAME)
    if await fields.count() > 2:
        await flows_set_platform_field(
            fields.nth(2), "Помощник интернет-магазина садовых товаров"
        )
    await scenario.step(
        "Создайте агента из шаблона",
        page,
        screenshot_name="agent-plan-create-wizard",
        label_en="Create an agent from a template",
        details=(
            "На главной Flows нажмите создание агента, выберите обычный шаблон и "
            "укажите название «Помощник Зелёного сада». Так у вас появится помощник "
            "с нодой ответа, готовый к настройке плана шагов."
        ),
        details_en=(
            "On the Flows home start creating an agent, pick the plain template, and "
            "name it Green Garden Assistant. You get an answer node ready for a "
            "step checklist setup."
        ),
    )
    await flows_click_platform_button(modal, "Создать", "Create", "Готово", "Done")
    studio_sections = page.get_by_role(
        "group", name=re.compile(r"Agent editor sections", re.I)
    )
    canvas = page.locator("flows-flow-canvas").first
    try:
        await expect(studio_sections.first).to_be_visible(timeout=15_000)
    except AssertionError:
        await expect(canvas.locator("svg.canvas-host")).to_be_visible(timeout=30_000)
        await flows_e2e_switch_editor_layout(page, "agent")
        await expect(studio_sections.first).to_be_visible(timeout=30_000)


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="agent-plan-via-skill",
    title="План шагов агента через Skill",
    description=(
        "**Для чего:** эта инструкция научит подключить Skill планирования, чтобы "
        "в чате был видимый checklist шагов работы агента.\n\n"
        "**Какие проблемы решает:** длинные задачи агента непрозрачны — непонятно, "
        "на каком шаге он сейчас и как включить checklist без ручной настройки "
        "инструментов.\n\n"
        "**Результат:** у «Помощника Зелёного сада» в чате появляется план шагов; "
        "готовые шаги зачёркнуты, текущий выделен."
    ),
    title_en="Agent step plan via Skill",
    description_en=(
        "**What for:** this guide shows how to attach the planning Skill so chat shows "
        "a visible checklist of the agent's steps.\n\n"
        "**Problems it solves:** long agent tasks are opaque — you cannot see the "
        "current step or enable a checklist without wiring tools by hand.\n\n"
        "**Result:** the Green Garden Assistant chat shows a step plan; completed "
        "steps are struck through and the current one is highlighted."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_agent_plan_via_skill(
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
    page = ui_page_system
    flow_id = flows_doc_flow_id("plan_skill", unique_id)
    await flows_e2e_ensure_platform_skills_seed(flows_ui.origin, auth_token_system)

    await _create_agent_wizard_steps(
        scenario, page, flows_ui, flow_id=flow_id
    )

    await flows_e2e_open_studio_skills_tools(page)
    await scenario.step(
        "Откройте студию в режиме «Инструменты»",
        page,
        screenshot_name="agent-plan-studio-tools",
        label_en="Open Studio in Tools mode",
        details=(
            "В студии агента откройте секцию Skills и tools и выберите режим "
            "«Инструменты». Только здесь можно подключить Skill планирования."
        ),
        details_en=(
            "In agent Studio open Skills and tools and choose Tools mode. Only here "
            "can you attach the planning Skill."
        ),
    )

    await flows_e2e_attach_skill_to_llm_node(page, _PLANNING_SKILL_ID)
    skill_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(re.escape(_PLANNING_SKILL_ID), re.I)
    ).first
    await expect(skill_chip).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте Skill планирования",
        page,
        screenshot_name="agent-plan-skill-attached",
        label_en="Add the planning Skill",
        details=(
            "Нажмите «Добавить skill», найдите «agent-planning» (Планирование) и "
            "подтвердите. На ноде появится чип Skill — вместе с ним агент получит "
            "инструменты записи и чтения плана шагов."
        ),
        details_en=(
            "Click Add skill, find agent-planning, and confirm. A Skill chip appears "
            "on the node — with it the agent gets tools to write and read the step plan."
        ),
    )

    await flows_publish_editor(page)
    await flows_open_chat_page(page, flows_ui, flow_id)
    chat = page.locator("flows-chat-page platform-flow-ui").first
    await expect(chat).to_be_visible(timeout=30_000)
    await scenario.step(
        "Опубликуйте агента и откройте чат",
        page,
        screenshot_name="agent-plan-chat-opened",
        label_en="Publish the agent and open chat",
        details=(
            "Опубликуйте изменения и откройте чат «Помощника Зелёного сада». Дальше "
            "покупатель пишет многошаговый запрос — агент покажет план прямо в ленте."
        ),
        details_en=(
            "Publish the changes and open the Green Garden Assistant chat. Next the "
            "customer sends a multi-step request — the agent shows the plan in the feed."
        ),
    )

    await flows_seed_mock_llm(
        flows_e2e_agent_plan_mock_writes(
            step1=_STEP_FIND,
            step2=_STEP_DELIVERY,
            step3=_STEP_CONFIRM,
            final_text=_FINAL_REPLY,
            load_skill_id=_PLANNING_SKILL_ID,
        )
    )
    await flows_chat_send_message(page, _USER_PROMPT)
    await flows_e2e_expect_agent_plan_block(
        page,
        completed_title=_STEP_FIND,
        in_progress_title=_STEP_DELIVERY,
    )
    await scenario.step(
        "Отправьте многошаговый запрос и увидьте checklist",
        page,
        screenshot_name="agent-plan-checklist-appeared",
        label_en="Send a multi-step request and see the checklist",
        details=(
            "Напишите запрос с несколькими действиями (найти заказ, проверить доставку, "
            "подтвердить состав). В ленте появится блок плана с шагами — это и есть "
            "видимый прогресс работы агента."
        ),
        details_en=(
            "Send a request with several actions (find the order, check delivery, "
            "confirm contents). A plan block with steps appears in the feed — that is "
            "the agent's visible progress."
        ),
    )

    reply = chat.get_by_text(re.compile(r"Заказ найден|доставка завтра", re.I)).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Проверьте обновление плана и ответ",
        page,
        screenshot_name="agent-plan-progress-demo",
        label_en="Check plan progress and the reply",
        details=(
            "**Демонстрация результата.** Готовый шаг «Найти заказ покупателя» "
            "зачёркнут, текущий — «Проверить статус доставки»; рядом краткий ответ "
            "агента о заказе.\n\n"
            "**Итог.** Вы умеете подключать Skill планирования и читать прогресс "
            "многошаговой задачи прямо в чате."
        ),
        details_en=(
            "**Result demonstration.** The completed step Find the customer order is "
            "struck through, the current one is Check delivery status; next to it is "
            "the agent's short order reply.\n\n"
            "**Summary.** You can attach the planning Skill and follow multi-step "
            "progress in chat."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="agent-plan-via-tools",
    title="План шагов агента через инструменты",
    description=(
        "**Для чего:** эта инструкция научит вручную подключить инструменты плана "
        "шагов, если Skill не нужен или недоступен.\n\n"
        "**Какие проблемы решает:** нужен только checklist в чате без процедуры "
        "Skill — достаточно инструментов записи и чтения плана.\n\n"
        "**Результат:** у «Помощника Зелёного сада» в чате тот же checklist с "
        "зачёркиванием готовых шагов."
    ),
    title_en="Agent step plan via tools",
    description_en=(
        "**What for:** this guide shows how to attach plan tools by hand when a Skill "
        "is not needed or not available.\n\n"
        "**Problems it solves:** you only need a chat checklist without a Skill "
        "procedure — write and read plan tools are enough.\n\n"
        "**Result:** the Green Garden Assistant chat shows the same checklist with "
        "completed steps struck through."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_agent_plan_via_tools(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
    flows_service,
) -> None:
    _ = secrets_service, taskiq_worker, flows_service, auth_token_system
    page = ui_page_system
    flow_id = flows_doc_flow_id("plan_tools", unique_id)

    await _create_agent_wizard_steps(
        scenario, page, flows_ui, flow_id=flow_id
    )

    await flows_e2e_open_studio_skills_tools(page)
    await scenario.step(
        "Откройте студию в режиме «Инструменты»",
        page,
        screenshot_name="agent-plan-tools-studio",
        label_en="Open Studio in Tools mode",
        details=(
            "В студии откройте секцию Skills и tools и выберите «Инструменты». "
            "Сюда добавляют инструменты из библиотеки — без Skill."
        ),
        details_en=(
            "In Studio open Skills and tools and choose Tools. Here you add library "
            "tools without a Skill."
        ),
    )

    await flows_llm_add_named_tool_from_library(page, "agent_plan_write")
    write_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(r"agent_plan_write", re.I)
    ).first
    await expect(write_chip).to_be_visible(timeout=30_000)
    await flows_llm_add_named_tool_from_library(page, "agent_plan_get")
    get_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(r"agent_plan_get", re.I)
    ).first
    await expect(get_chip).to_be_visible(timeout=30_000)
    await expect(write_chip).to_be_visible(timeout=15_000)
    await scenario.step(
        "Добавьте инструменты плана из библиотеки",
        page,
        screenshot_name="agent-plan-tools-attached",
        label_en="Add plan tools from the library",
        details=(
            "Нажмите «Из библиотеки» и добавьте agent_plan_write и agent_plan_get. "
            "Первый записывает весь checklist шагов, второй читает текущий план. "
            "Оба появятся чипами на ноде."
        ),
        details_en=(
            "Click From library and add agent_plan_write and agent_plan_get. "
            "The first writes the full step checklist; the second reads the current "
            "plan. Both appear as chips on the node."
        ),
    )

    await flows_publish_editor(page)
    await flows_open_chat_page(page, flows_ui, flow_id)
    chat = page.locator("flows-chat-page platform-flow-ui").first
    await expect(chat).to_be_visible(timeout=30_000)
    await scenario.step(
        "Опубликуйте агента и откройте чат",
        page,
        screenshot_name="agent-plan-tools-chat",
        label_en="Publish the agent and open chat",
        details=(
            "Опубликуйте настройки и откройте чат помощника. Дальше тот же многошаговый "
            "запрос покупателя — план появится без Skill."
        ),
        details_en=(
            "Publish the settings and open the assistant chat. Next the same multi-step "
            "customer request — the plan appears without a Skill."
        ),
    )

    await flows_seed_mock_llm(
        flows_e2e_agent_plan_mock_writes(
            step1=_STEP_FIND,
            step2=_STEP_DELIVERY,
            step3=_STEP_CONFIRM,
            final_text=_FINAL_REPLY,
            load_skill_id=None,
        )
    )
    await flows_chat_send_message(page, _USER_PROMPT)
    await flows_e2e_expect_agent_plan_block(
        page,
        completed_title=_STEP_FIND,
        in_progress_title=_STEP_DELIVERY,
    )
    await scenario.step(
        "Отправьте многошаговый запрос и увидьте checklist",
        page,
        screenshot_name="agent-plan-tools-checklist",
        label_en="Send a multi-step request and see the checklist",
        details=(
            "Напишите запрос с несколькими действиями. Агент вызовет инструменты "
            "плана, и в ленте появится checklist шагов."
        ),
        details_en=(
            "Send a request with several actions. The agent calls the plan tools, and "
            "a step checklist appears in the feed."
        ),
    )

    reply = chat.get_by_text(re.compile(r"Заказ найден|доставка завтра", re.I)).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Проверьте обновление плана и ответ",
        page,
        screenshot_name="agent-plan-tools-progress-demo",
        label_en="Check plan progress and the reply",
        details=(
            "**Демонстрация результата.** Шаг «Найти заказ покупателя» зачёркнут, "
            "текущий — «Проверить статус доставки»; рядом ответ агента.\n\n"
            "**Итог.** Вы умеете включать план шагов вручную через инструменты "
            "библиотеки и следить за прогрессом в чате."
        ),
        details_en=(
            "**Result demonstration.** Find the customer order is struck through, "
            "Check delivery status is current; the agent reply is next to it.\n\n"
            "**Summary.** You can enable a step plan via library tools and follow "
            "progress in chat."
        ),
    )

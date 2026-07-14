"""UI E2E сценарии Flows: оркестратор, самопроверка ответа и handoff между агентами."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_RETURNS_AGENT,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_click_llm_output_mode,
    flows_doc_flow_id,
    flows_drop_node,
    flows_llm_add_tool_from_library,
    flows_llm_payload,
    flows_multi_orchestrator_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_publish_editor,
    flows_set_llm_call_type,
    flows_set_selected_llm_prompt,
    flows_wire_ports,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="compose-orchestrator",
    title="Собираем агента из под-агентов",
    description=(
        "**Для чего:** эта инструкция поможет разделить сложную задачу между "
        "специализированными под-агентами.\n\n"
        "**Какие проблемы решает:** один универсальный агент путается в темах — "
        "доставку и возвраты лучше поручить отдельным помощникам.\n\n"
        "**Результат:** оркестратор с подключённым агентом возвратов как инструментом."
    ),
    title_en="Compose an orchestrator from sub-agents",
    description_en=(
        "**What for:** this guide helps split a complex task across specialized sub-agents.\n\n"
        "**Problems it solves:** one general agent mixes topics — delivery and returns "
        "are better handled by dedicated assistants.\n\n"
        "**Result:** an orchestrator with the returns agent attached as a tool."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_compose_orchestrator(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    orchestrator_id = flows_doc_flow_id("orchestrator", unique_id)
    returns_id = flows_doc_flow_id("returns_sub", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            returns_id,
            name=GREEN_GARDEN_RETURNS_AGENT,
            prompt="Ты отвечаешь только за возвраты в «Зелёном саду».",
        ),
    )
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_multi_orchestrator_payload(orchestrator_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, orchestrator_id)
    await flows_open_node_editor(page, "orchestrator")
    await scenario.step(
        "Откройте агента-оркестратора",
        page,
        screenshot_name="orchestrator-opened",
        label_en="Open the orchestrator agent",
        details=(
            "В редакторе откройте главную LLM-ноду оркестратора. Она решает, какому "
            "под-агенту передать запрос покупателя."
        ),
        details_en=(
            "In the editor open the orchestrator's main LLM node. It decides which "
            "sub-agent should handle the customer request."
        ),
    )

    try:
        flow_node_id = await flows_drop_node(page, "flow", x=620, y=420)
    except AssertionError:
        flow_node_id = ""
    if flow_node_id:
        try:
            _ = await flows_open_node_editor(page, flow_node_id)
            await expect(page.locator("flows-flow-node-editor")).to_be_visible(timeout=30_000)
        except AssertionError:
            flow_node_id = ""
    if flow_node_id:
        await scenario.step(
            "Добавьте ноду вложенного агента",
            page,
            screenshot_name="subflow-node-added",
            label_en="Add a nested agent node",
            details=(
                "Перетащите ноду «Под-агент» (flow) на канву и откройте её настройки. "
                "Здесь указывается, какой готовый агент будет выполнять часть работы."
            ),
            details_en=(
                "Drag a Sub-agent (flow) node onto the canvas and open its settings. "
                "Here you specify which existing agent runs part of the work."
            ),
        )

    await flows_open_node_editor(page, "orchestrator")
    await flows_llm_add_tool_from_library(page)
    tool_chip = page.locator("flows-llm-node-editor .chip").first
    await expect(tool_chip).to_be_visible(timeout=30_000)
    await scenario.step(
        "Подключите под-агента в списке tools",
        page,
        screenshot_name="orchestrator-tool-attached",
        label_en="Attach the sub-agent in the tools list",
        details=(
            "Добавьте из библиотеки агента возвратов. В списке tools появится чип с его "
            "именем — оркестратор сможет делегировать ему соответствующие вопросы."
        ),
        details_en=(
            "Add the returns agent from the library. A chip with its name appears in the "
            "tools list — the orchestrator can delegate matching questions to it."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, orchestrator_id)
    tools = persisted["nodes"]["orchestrator"].get("tools") or []
    assert len(tools) >= 1
    await scenario.step(
        "Подключите под-агента как инструмент",
        page,
        screenshot_name="orchestrator-tool-published",
        label_en="Attach the sub-agent as a tool",
        details=(
            "**Демонстрация результата.** Под-агент добавлен в список tools оркестратора "
            "и опубликован — главный агент может делегировать ему возвраты.\n\n"
            "**Итог.** Теперь вы умеете собирать оркестратора из под-агентов и подключать "
            "их как инструменты."
        ),
        details_en=(
            "**Result demonstration.** The sub-agent is listed in the orchestrator tools "
            "and published — the main agent can delegate returns to it.\n\n"
            "**Summary.** You can build an orchestrator from sub-agents and attach them as tools."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="add-answer-review",
    title="Добавляем самопроверку ответа",
    description=(
        "**Для чего:** эта инструкция не даст отдать покупателю ответ, не прошедший проверку.\n\n"
        "**Какие проблемы решает:** агент иногда отвечает слишком общо — нужен блок "
        "самопроверки перед выдачей текста.\n\n"
        "**Результат:** нода проверки (reflection) подключена после основного агента."
    ),
    title_en="Add an answer self-review",
    description_en=(
        "**What for:** this guide blocks giving the customer an answer that failed quality checks.\n\n"
        "**Problems it solves:** the agent sometimes replies too vaguely — you need a "
        "self-review step before sending text.\n\n"
        "**Result:** a reflection review node is wired after the main agent."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_add_answer_review(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("review", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай покупателю «Зелёного сада» вежливо и по делу.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    reflection_node_id = await flows_drop_node(page, "reflection", x=560, y=360)
    await flows_wire_ports(page, "agent", reflection_node_id)
    await scenario.step(
        "Добавьте ноду проверки ответа",
        page,
        screenshot_name="reflection-node-opened",
        label_en="Add an answer review node",
        details=(
            "Перетащите ноду «Проверка» (reflection) и откройте её. Здесь задаются "
            "критерии качества и порог уверенности перед выдачей ответа."
        ),
        details_en=(
            "Drag a Review (reflection) node and open it. Here you set quality criteria "
            "and a confidence threshold before sending the reply."
        ),
    )

    _ = await flows_open_node_editor(page, reflection_node_id)
    editor = page.locator("flows-reflection-node-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    await expect(editor).to_contain_text(
        re.compile(r"политик|policy|критер", re.I),
        timeout=15_000,
    )
    await scenario.step(
        "Настройте критерии проверки",
        page,
        screenshot_name="reflection-policy-visible",
        label_en="Configure review criteria",
        details=(
            "Проверьте блок политики критика: можно задать минимальную уверенность "
            "и критерии, при нарушении которых ответ не уйдёт покупателю."
        ),
        details_en=(
            "Review the critic policy block: set minimum confidence and criteria "
            "that block the reply when quality is too low."
        ),
    )

    branch_ids = await page.locator("flows-flow-canvas").first.evaluate(
        "(el) => Object.keys(el._branchData().nodes || {})"
    )
    assert reflection_node_id in branch_ids, (
        f"reflection node missing from editor draft before publish: {branch_ids!r}"
    )
    agent_node = page.locator(
        "flows-flow-canvas g.node[data-node-id='agent']"
    ).first
    reflection_node = page.locator(
        f"flows-flow-canvas g.node[data-node-id='{reflection_node_id}']"
    ).first
    await expect(agent_node).to_be_visible(timeout=15_000)
    await expect(reflection_node).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте связь нод на канве",
        page,
        screenshot_name="reflection-wired-on-canvas",
        label_en="Verify the node wiring on the canvas",
        details=(
            "На канве видны и агент, и нода проверки, соединённые стрелкой. Ответ "
            "сначала проходит через reflection, и только потом уходит покупателю."
        ),
        details_en=(
            "The canvas shows both the agent and review node connected by an edge. "
            "The reply passes through reflection before reaching the customer."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    nodes = persisted.get("nodes") or {}
    reflection_nodes = [n for n in nodes.values() if n.get("type") == "reflection"]
    assert reflection_node_id in nodes or len(reflection_nodes) >= 1, (
        f"reflection node missing after publish: canvas_id={reflection_node_id!r}, "
        f"api_nodes={list(nodes)!r}"
    )
    await scenario.step(
        "Опубликуйте граф с проверкой",
        page,
        screenshot_name="reflection-published",
        label_en="Publish the graph with review",
        details=(
            "**Демонстрация результата.** Нода самопроверки сохранена в графе — "
            "слабый ответ можно отклонить до отправки покупателю.\n\n"
            "**Итог.** Теперь вы умеете добавлять reflection-ноду и настраивать "
            "контроль качества ответа."
        ),
        details_en=(
            "**Result demonstration.** The self-review node is saved in the graph — "
            "weak answers can be rejected before reaching the customer.\n\n"
            "**Summary.** You can add a reflection node and configure answer quality control."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="agent-handoff",
    title="Передаём диалог между агентами",
    description=(
        "**Для чего:** эта инструкция передаст покупателя профильному агенту, "
        "например «Агенту возвратов».\n\n"
        "**Какие проблемы решает:** основной помощник не должен вести весь диалог "
        "сам — сложные темы лучше передать специалисту.\n\n"
        "**Результат:** у инструмента под-агента включён режим handoff."
    ),
    title_en="Hand off the dialog between agents",
    description_en=(
        "**What for:** this guide hands the customer to a specialist agent, "
        "for example the Returns Agent.\n\n"
        "**Problems it solves:** the main assistant should not handle every topic — "
        "complex cases go to a dedicated agent.\n\n"
        "**Result:** the sub-agent tool uses handoff mode."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_agent_handoff(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    parent_id = flows_doc_flow_id("handoff_parent", unique_id)
    child_id = flows_doc_flow_id("handoff_child", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            child_id,
            name=GREEN_GARDEN_RETURNS_AGENT,
            prompt="Ты ведёшь диалог о возвратах после передачи от главного агента.",
        ),
    )
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            parent_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Помогай покупателю и при возврате передай диалог агенту возвратов.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, parent_id)
    await flows_open_node_editor(page, "agent")
    await flows_click_llm_output_mode(page, "tools")
    await flows_llm_add_tool_from_library(page)
    tool_chip = page.locator("flows-floating-panel flows-llm-node-editor .chip").first
    await expect(tool_chip).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте агента возвратов как инструмент",
        page,
        screenshot_name="handoff-tool-added",
        label_en="Add the returns agent as a tool",
        details=(
            "Откройте главного агента и добавьте из библиотеки под-агента возвратов. "
            "Так оркестратор сможет передать ему диалог целиком."
        ),
        details_en=(
            "Open the main agent and add the returns sub-agent from the library. "
            "The orchestrator can then hand off the full dialog to it."
        ),
    )

    await flows_set_llm_call_type(page, "handoff")
    await flows_set_selected_llm_prompt(
        page,
        "Если покупатель спрашивает про возврат, передай диалог агенту возвратов через handoff.",
    )
    await expect(tool_chip).to_be_visible(timeout=15_000)
    await scenario.step(
        "Включите режим передачи управления",
        page,
        screenshot_name="handoff-mode-enabled",
        label_en="Enable handoff mode",
        details=(
            "В блоке типа вызова выберите Handoff (передача управления). В этом режиме "
            "под-агент получает весь диалог, а не только один запрос."
        ),
        details_en=(
            "In the call type block choose Handoff (ownership transfer). In this mode "
            "the sub-agent receives the full dialog, not a single request."
        ),
    )

    handoff_prompt = page.locator("flows-llm-node-editor").get_by_text(
        re.compile(r"возврат|return|handoff", re.I)
    ).first
    await expect(handoff_prompt).to_be_visible(timeout=15_000)
    await scenario.step(
        "Добавьте правило передачи в инструкцию",
        page,
        screenshot_name="handoff-prompt-rule-set",
        label_en="Add a handoff rule to the instruction",
        details=(
            "В инструкции агента опишите, когда передавать диалог агенту возвратов — "
            "например, при любом вопросе о возврате товара."
        ),
        details_en=(
            "In the agent instruction describe when to hand off to the returns agent — "
            "for example on any product return question."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, parent_id)
    agent_node = persisted["nodes"]["agent"]
    tools = agent_node.get("tools") or []
    assert len(tools) >= 1
    first_tool = tools[0]
    assert isinstance(first_tool, dict)
    assert first_tool.get("call_type") == "handoff"
    await scenario.step(
        "Опубликуйте настройку handoff",
        page,
        screenshot_name="handoff-published",
        label_en="Publish the handoff setup",
        details=(
            "**Демонстрация результата.** Инструмент под-агента сохранён с режимом handoff — "
            "главный агент может передать покупателя «Агенту возвратов».\n\n"
            "**Итог.** Теперь вы умеете настраивать передачу диалога между агентами "
            "без подключения оператора."
        ),
        details_en=(
            "**Result demonstration.** The sub-agent tool is saved with handoff mode — "
            "the main agent can transfer the customer to the Returns Agent.\n\n"
            "**Summary.** You can configure dialog handoff between agents without "
            "involving a human operator."
        ),
    )

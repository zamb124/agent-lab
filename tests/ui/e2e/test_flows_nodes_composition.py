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
    flows_execution_send_message,
    flows_llm_add_tool_from_library,
    flows_llm_payload,
    flows_multi_orchestrator_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_publish_editor,
    flows_seed_mock_llm,
    flows_set_llm_call_type,
    flows_set_selected_llm_prompt,
    flows_switch_editor_mode,
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

    await flows_set_selected_llm_prompt(
        page,
        "Определи тему запроса. Вопросы о возврате передавай агенту возвратов.",
    )
    await scenario.step(
        "Задайте правило делегирования",
        page,
        screenshot_name="orchestrator-routing-rule",
        label_en="Set the delegation rule",
        details=(
            "В поле промпта укажите, какие обращения должен передавать оркестратор. "
            "Явное правило про возвраты помогает ему выбирать специализированного "
            "помощника по смыслу запроса, а не отвечать на все темы самостоятельно."
        ),
        details_en=(
            "In the prompt field, state which requests the orchestrator should delegate. "
            "An explicit returns rule helps it choose the specialized assistant from the "
            "request meaning instead of answering every topic itself."
        ),
    )

    await flows_open_node_editor(page, "orchestrator")
    await flows_llm_add_tool_from_library(page, returns_id)
    tool_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(re.escape(GREEN_GARDEN_RETURNS_AGENT), re.I)
    ).first
    await expect(tool_chip).to_be_visible(timeout=5_000)
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
    timeout_seconds=60,
    title="Передаём диалог между агентами",
    description=(
        "**Для чего:** эта инструкция покажет полный цикл взаимодействия агентов: "
        "передачу покупателя профильному агенту и возврат управления назад.\n\n"
        "**Какие проблемы решает:** основной помощник не должен вести весь диалог "
        "сам, а пользователь должен всегда видеть, кто именно ему отвечает.\n\n"
        "**Результат:** в реальном чате видны передача, ответ «Агента возвратов», "
        "возврат управления и следующий ответ главного агента."
    ),
    title_en="Hand off the dialog between agents",
    description_en=(
        "**What for:** this guide demonstrates the complete agent collaboration cycle: "
        "handoff to a specialist and control returned to the parent.\n\n"
        "**Problems it solves:** the main assistant should not handle every topic, and "
        "the user must always see who is replying.\n\n"
        "**Result:** the real chat shows the transfer, a Returns Agent reply, handback, "
        "and the next reply from the main agent."
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
            prompt=(
                "Ты ведёшь диалог о возвратах после передачи от главного агента. "
                "Когда вопрос решён, вызови handback_to_parent."
            ),
            tools=[{"tool_id": "handback_to_parent"}],
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
    studio = page.locator("flows-agent-focus-studio").first
    await expect(studio).to_be_visible(timeout=30_000)
    await flows_set_selected_llm_prompt(
        page,
        "Если покупатель спрашивает про возврат, передай диалог агенту возвратов через handoff.",
    )
    skills_tab = studio.locator("platform-segmented-control").get_by_role(
        "button", name=re.compile(r"Skills|Tools|Инструмент", re.I)
    ).first
    await expect(skills_tab).to_be_visible(timeout=15_000)
    await skills_tab.click()
    await flows_click_llm_output_mode(page, "tools")
    await flows_llm_add_tool_from_library(page, child_id)
    tool_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(re.escape(GREEN_GARDEN_RETURNS_AGENT), re.I)
    ).first
    await expect(tool_chip).to_be_visible(timeout=5_000)
    await scenario.step(
        "Добавьте агента возвратов как инструмент",
        page,
        screenshot_name="handoff-tool-added",
        label_en="Add the returns agent as a tool",
        details=(
            "Откройте главного агента и добавьте из библиотеки под-агента возвратов. "
            "На одном таком чипе режим **Call** вызывает под-агента один раз и возвращает "
            "результат текущему агенту; активным остаётся главный агент."
        ),
        details_en=(
            "Open the main agent and add the returns sub-agent from the library. "
            "On this chip, **Call** invokes the sub-agent once and returns its result to "
            "the current agent; the main agent remains active."
        ),
    )

    await flows_set_llm_call_type(page, "handoff")
    await expect(tool_chip).to_be_visible(timeout=15_000)
    await scenario.step(
        "Включите режим передачи управления",
        page,
        screenshot_name="handoff-mode-enabled",
        label_en="Enable handoff mode",
        details=(
            "Нажмите **Call** на чипе — он переключится в **Handoff**. Затем в инструкции "
            "опишите, когда передавать управление. После handoff следующие сообщения "
            "пользователя направляются под-агенту. Текущий текст и явно заданные переменные "
            "передаются автоматически; историю нужно подключать отдельно через срез сообщений."
        ),
        details_en=(
            "Click **Call** on the chip to switch it to **Handoff**, then describe when to "
            "transfer control. Following user turns are routed to the sub-agent. The current "
            "text and explicit variables are passed automatically; message history must be "
            "mapped separately when it is needed."
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
    await flows_switch_editor_mode(page, "run")
    run_chat = page.locator("flows-execution-panel platform-chat").first
    await expect(run_chat).to_be_visible(timeout=15_000)
    await scenario.step(
        "Опубликуйте и откройте режим запуска",
        page,
        screenshot_name="handoff-run-opened",
        label_en="Publish and open Run mode",
        details=(
            "Опубликуйте граф и включите **Запуск**. Справа откроется тот же общий чат, "
            "который используется на странице агента и во встраиваемом виджете."
        ),
        details_en=(
            "Publish the graph and switch to **Run**. The shared chat used on the agent "
            "page and in the embedded widget opens on the right."
        ),
    )

    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": child_id,
                "args": {"request": "Оформить возврат заказа GG-1042"},
            },
            {
                "type": "text",
                "content": "Я Агент возвратов и готов принять детали возврата.",
            },
        ]
    )
    await flows_execution_send_message(page, "Хочу вернуть заказ GG-1042")
    handoff_card = run_chat.locator("flows-chat-message[data-role='handoff'] .handoff-card").last
    await expect(handoff_card).to_be_visible(timeout=120_000)
    await expect(handoff_card).to_contain_text(GREEN_GARDEN_RETURNS_AGENT)
    await scenario.step(
        "Передайте диалог профильному агенту",
        page,
        screenshot_name="handoff-visible-in-chat",
        label_en="Hand off the dialog to the specialist",
        details=(
            "Отправьте вопрос о возврате. В ленте появится отдельная карточка передачи "
            f"управления агенту «{GREEN_GARDEN_RETURNS_AGENT}». Это не обычный ответ: "
            "следующая реплика пользователя уже пойдёт дочернему агенту."
        ),
        details_en=(
            "Send a return question. The feed shows a dedicated control-transfer card for "
            f"{GREEN_GARDEN_RETURNS_AGENT}. This is not a normal reply: the next user turn "
            "is routed to the child agent."
        ),
    )

    child_reply_text = "Я Агент возвратов. Заказ GG-1042 найден, готовлю возврат."
    await flows_seed_mock_llm([{"type": "text", "content": child_reply_text}])
    await flows_execution_send_message(page, "Товар не использован, упаковка сохранена")
    child_bubble = run_chat.locator("flows-chat-message[data-role='assistant']").filter(
        has_text=re.compile(r"Заказ GG-1042 найден", re.I)
    ).last
    await expect(child_bubble).to_be_visible(timeout=120_000)
    child_author = child_bubble.locator(
        ".author-identity[data-author-kind='subagent']"
    )
    await expect(child_author).to_be_visible(timeout=15_000)
    await expect(child_author).to_contain_text(GREEN_GARDEN_RETURNS_AGENT)
    await scenario.step(
        "Убедитесь, что отвечает субагент",
        page,
        screenshot_name="subagent-author-visible",
        label_en="Verify that the sub-agent is replying",
        details=(
            "Ответ помечен синей иконкой, именем «Агент возвратов» и ролью «Субагент». "
            "Так в длинном диалоге сразу видно, кто написал каждый bubble."
        ),
        details_en=(
            "The reply is marked with a blue icon, the Returns Agent name, and the "
            "Sub-agent role. Every bubble remains attributable in a long conversation."
        ),
    )

    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": "handback_to_parent",
                "args": {
                    "response": "Возврат GG-1042 оформлен",
                    "variables": {"return_id": "RET-1042"},
                },
            }
        ]
    )
    await flows_execution_send_message(page, "Оформите возврат и верните меня помощнику")
    handback_card = run_chat.locator(
        "flows-chat-message[data-role='handback'] .handback-card"
    ).last
    await expect(handback_card).to_be_visible(timeout=120_000)
    await expect(handback_card).to_contain_text("Возврат GG-1042 оформлен")
    await scenario.step(
        "Верните управление главному агенту",
        page,
        screenshot_name="handback-visible-in-chat",
        label_en="Return control to the main agent",
        details=(
            "Когда задача решена, дочерний агент вызывает **handback_to_parent**. В чат "
            "добавляется карточка возврата. Назад уходят только текст результата и явно "
            "указанные переменные — здесь это return_id."
        ),
        details_en=(
            "When the task is complete, the child calls **handback_to_parent**. A handback "
            "card is added to the feed. Only the result text and explicitly selected "
            "variables are returned — return_id in this example."
        ),
    )

    parent_reply_text = "Главный агент снова на связи. Возврат RET-1042 подтверждён."
    await flows_seed_mock_llm([{"type": "text", "content": parent_reply_text}])
    await flows_execution_send_message(page, "Спасибо, что дальше?")
    parent_bubble = run_chat.locator("flows-chat-message[data-role='assistant']").filter(
        has_text=re.compile(r"Главный агент снова на связи", re.I)
    ).last
    await expect(parent_bubble).to_be_visible(timeout=120_000)
    parent_author = parent_bubble.locator(".author-identity[data-author-kind='agent']")
    await expect(parent_author).to_be_visible(timeout=15_000)
    await expect(parent_author).to_contain_text(GREEN_GARDEN_AGENT_NAME)
    await scenario.step(
        "Проверьте возврат к главному агенту",
        page,
        screenshot_name="parent-author-restored",
        label_en="Verify the return to the main agent",
        details=(
            "**Демонстрация результата.** Следующий ответ снова подписан именем главного "
            "агента и ролью «Агент». В одной ленте виден весь цикл: пользователь → агент → "
            "handoff → субагент → handback → агент.\n\n"
            "**Итог.** Используйте Call для разового запроса с возвратом результата, Handoff "
            "для передачи следующих реплик и handback_to_parent для явного возврата управления."
        ),
        details_en=(
            "**Result demonstration.** The next reply is again labelled with the main agent "
            "name and Agent role. One feed shows the complete cycle: user → agent → handoff → "
            "sub-agent → handback → agent.\n\n"
            "**Summary.** Use Call for a one-off invocation, Handoff to route following turns, "
            "and handback_to_parent to explicitly return control."
        ),
    )

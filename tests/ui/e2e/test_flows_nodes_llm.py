"""UI E2E сценарии Flows: LLM-нода — инструменты и структурированный ответ."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_click_llm_output_mode,
    flows_close_floating_panel,
    flows_doc_flow_id,
    flows_e2e_ensure_canvas_layout,
    flows_execution_send_message,
    flows_llm_add_named_tool_from_library,
    flows_llm_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_publish_editor,
    flows_seed_mock_llm,
    flows_set_selected_llm_prompt,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_ORDER_SCHEMA_SNIPPET = '"order_id"'


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="add-agent-tools",
    title="Даём агенту инструменты",
    description=(
        "**Для чего:** эта инструкция научит подключать к агенту инструменты, "
        "чтобы он мог выполнять действия, а не только отвечать текстом.\n\n"
        "**Какие проблемы решает:** без инструментов агент ограничен словами и не может "
        "обращаться к внешним сервисам или внутренним операциям магазина.\n\n"
        "**Результат:** у «Помощника Зелёного сада» появится калькулятор из библиотеки, "
        "и в тестовом запуске будет виден вызов инструмента."
    ),
    title_en="Give the agent tools",
    description_en=(
        "**What for:** this guide shows how to attach tools to an agent so it can take "
        "actions, not only reply in text.\n\n"
        "**Problems it solves:** without tools the agent is limited to words and cannot "
        "call store services or internal operations.\n\n"
        "**Result:** the Green Garden Assistant gets a calculator from the library, and "
        "a test run shows the tool call."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_add_agent_tools(
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
    flow_id = flows_doc_flow_id("add_tools", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt=(
                "Помогай покупателю «Зелёного сада». Если нужна арифметика — "
                "вызови calculator."
            ),
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_ensure_canvas_layout(page)
    await flows_open_node_editor(page, "agent")
    await scenario.step(
        "Откройте агента в редакторе",
        page,
        screenshot_name="agent-editor-opened",
        label_en="Open the agent in the editor",
        details=(
            "Откройте агента на канве и перейдите в настройки. Здесь задаётся поведение "
            "и список инструментов. Skills (процедуры) — отдельная секция рядом; "
            "их подключение описано в инструкции про Skills."
        ),
        details_en=(
            "Open the agent on the canvas and open settings. Here you set behavior and "
            "tools. Skills (procedures) are a separate section nearby; attaching them is "
            "covered in the Skills guide."
        ),
    )

    await flows_click_llm_output_mode(page, "tools")
    tools_section = page.locator("flows-llm-node-editor").get_by_text(
        re.compile(r"Инструменты|Tools")
    ).first
    await expect(tools_section).to_be_visible(timeout=15_000)
    await scenario.step(
        "Переключите ноду в режим инструментов",
        page,
        screenshot_name="tools-mode-active",
        label_en="Switch the node to tools mode",
        details=(
            "В блоке «Режим вывода» выберите «Инструменты». В этом режиме агент может "
            "вызывать операции. Режим «Структурированный» для tools и Skills не подходит."
        ),
        details_en=(
            "In Output mode choose Tools. In this mode the agent can call operations. "
            "Structured mode is not for tools or Skills."
        ),
    )

    await flows_llm_add_named_tool_from_library(page, "calculator")
    tool_chip = page.locator("flows-llm-node-editor .chip").filter(
        has_text=re.compile(r"calculator", re.I)
    ).first
    await expect(tool_chip).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте инструмент из библиотеки",
        page,
        screenshot_name="tool-added-from-library",
        label_en="Add a tool from the library",
        details=(
            "Нажмите «Из библиотеки» и выберите calculator. После выбора он появится "
            "чипом в списке инструментов ноды."
        ),
        details_en=(
            "Click From library and pick calculator. After selection it appears as a "
            "chip in the node tool list."
        ),
    )

    await flows_publish_editor(page)
    await flows_close_floating_panel(page)
    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": "calculator",
                "args": {"expression": "2+2"},
            },
            {"type": "text", "content": "Сумма заказа с доставкой: 4."},
        ]
    )
    await flows_execution_send_message(page, "Посчитай 2+2 для скидки")
    reply = page.locator("flows-execution-panel platform-chat").get_by_text(
        re.compile(r"4|Сумма"), exact=False
    ).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Запустите агента и увидьте вызов инструмента",
        page,
        screenshot_name="tool-call-in-run",
        label_en="Run the agent and see the tool call",
        details=(
            "**Демонстрация результата.** Перейдите в режим запуска, задайте вопрос с "
            "расчётом — агент вызовет calculator, и в ответе появится результат.\n\n"
            "**Итог.** Теперь вы умеете включать режим инструментов, добавлять tool из "
            "библиотеки и проверять вызов в тестовом запуске."
        ),
        details_en=(
            "**Result demonstration.** Switch to Run mode, ask a calculation question — "
            "the agent calls calculator and the reply shows the result.\n\n"
            "**Summary.** You can enable tools mode, add a library tool, and verify the "
            "call in a test run."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="structured-answer",
    title="Строгий JSON-ответ агента",
    description=(
        "**Для чего:** эта инструкция поможет получать ответ агента в заданной JSON-структуре "
        "для дальнейшей обработки в графе.\n\n"
        "**Какие проблемы решает:** свободный текст сложно передать следующей ноде — "
        "нужен предсказуемый формат полей заказа.\n\n"
        "**Результат:** агент настроен на структурированный вывод со схемой JSON."
    ),
    title_en="Get a strict JSON answer",
    description_en=(
        "**What for:** this guide helps you get agent replies in a fixed JSON shape "
        "for downstream processing in the graph.\n\n"
        "**Problems it solves:** free text is hard to pass to the next node — you need "
        "predictable order fields.\n\n"
        "**Result:** the agent is configured for structured output with a JSON schema."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_structured_answer(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("structured", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Верни данные заказа покупателя в структурированном виде.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_ensure_canvas_layout(page)
    await flows_open_node_editor(page, "agent")
    await scenario.step(
        "Откройте настройки агента",
        page,
        screenshot_name="structured-editor-opened",
        label_en="Open agent settings",
        details=(
            "В редакторе ноды найдите блок «Режим вывода». Он определяет, будет ли ответ "
            "обычным текстом с инструментами или строгим JSON."
        ),
        details_en=(
            "In the node editor find the Output mode block. It decides whether the reply "
            "is plain text with tools or strict JSON."
        ),
    )

    await flows_click_llm_output_mode(page, "structured")
    schema_editor = page.locator("flows-llm-node-editor platform-json-editor").first
    await expect(schema_editor).to_be_visible(timeout=15_000)
    skills_heading = page.locator("flows-llm-node-editor").get_by_text(
        re.compile(r"^Skills$|Agent Skills")
    )
    await expect(skills_heading).to_have_count(0)
    await scenario.step(
        "Включите структурированный вывод",
        page,
        screenshot_name="structured-mode-enabled",
        label_en="Enable structured output",
        details=(
            "Переключите режим на «Структурированный». Появится редактор JSON-схемы. "
            "Секция Skills в этом режиме скрыта — процедуры и meta-tools работают только "
            "в режиме «Инструменты»."
        ),
        details_en=(
            "Switch the mode to Structured. A JSON schema editor appears. The Skills "
            "section is hidden in this mode — procedures and meta-tools work only in "
            "Tools mode."
        ),
    )

    await flows_set_selected_llm_prompt(
        page,
        "Верни JSON с полями order_id, status и delivery_city для заказа покупателя.",
    )
    await scenario.step(
        "Уточните схему и инструкцию",
        page,
        screenshot_name="schema-and-prompt-set",
        label_en="Refine schema and instruction",
        details=(
            "Проверьте схему вывода и допишите в инструкции, какие поля нужны магазину. "
            "Так агент понимает, какой JSON ожидает следующий шаг графа."
        ),
        details_en=(
            "Review the output schema and extend the instruction with the fields the "
            "store needs. This tells the agent what JSON the next graph step expects."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    agent_node = persisted["nodes"]["agent"]
    assert agent_node.get("structured_output") is True, agent_node
    schema_text = str(agent_node.get("output_schema") or "")
    assert _ORDER_SCHEMA_SNIPPET in schema_text or "properties" in schema_text
    await scenario.step(
        "Опубликуйте и проверьте настройку",
        page,
        screenshot_name="structured-output-published",
        label_en="Publish and verify the setting",
        details=(
            "**Демонстрация результата.** После публикации режим структурированного вывода "
            "и JSON-схема сохранены в агенте — их видно при повторном открытии ноды.\n\n"
            "**Итог.** Теперь вы умеете включать структурированный вывод и задавать схему "
            "ответа для автоматической обработки данных заказа."
        ),
        details_en=(
            "**Result demonstration.** After publishing, structured mode and the JSON "
            "schema are saved on the agent and visible when you reopen the node.\n\n"
            "**Summary.** You can enable structured replies and define a response schema "
            "for automatic order data processing."
        ),
    )

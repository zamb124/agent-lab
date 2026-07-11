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
    flows_doc_flow_id,
    flows_llm_add_tool_from_library,
    flows_llm_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_publish_editor,
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
        "**Результат:** у «Помощника Зелёного сада» появится инструмент из библиотеки "
        "и опубликованная версия агента."
    ),
    title_en="Give the agent tools",
    description_en=(
        "**What for:** this guide shows how to attach tools to an agent so it can take "
        "actions, not only reply in text.\n\n"
        "**Problems it solves:** without tools the agent is limited to words and cannot "
        "call store services or internal operations.\n\n"
        "**Result:** the Green Garden Assistant gets a library tool and a published version."
    ),
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
) -> None:
    _ = secrets_service, taskiq_worker
    flow_id = flows_doc_flow_id("add_tools", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Помогай покупателю «Зелёного сада» и при необходимости вызывай инструменты.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_node_editor(page, "agent")
    await scenario.step(
        "Откройте агента в редакторе",
        page,
        screenshot_name="agent-editor-opened",
        label_en="Open the agent in the editor",
        details=(
            "Откройте агента на канве и перейдите в его настройки. Здесь задаётся поведение "
            "и список инструментов, которые агент может вызывать сам."
        ),
        details_en=(
            "Open the agent on the canvas and go to its settings. This is where you set "
            "behavior and the list of tools the agent can call on its own."
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
            "В блоке «Режим вывода» оставьте «Инструменты». В этом режиме агент может "
            "вызывать подключённые операции и использовать их результат в ответе."
        ),
        details_en=(
            "In the Output mode block keep Tools selected. In this mode the agent can "
            "call attached operations and use their results in the reply."
        ),
    )

    await flows_llm_add_tool_from_library(page)
    tool_chip = page.locator("flows-llm-node-editor .chip").first
    await expect(tool_chip).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте инструмент из библиотеки",
        page,
        screenshot_name="tool-added-from-library",
        label_en="Add a tool from the library",
        details=(
            "Нажмите «Из библиотеки» и выберите подходящий инструмент. После выбора "
            "он появится чипом в списке инструментов ноды."
        ),
        details_en=(
            "Click From library and pick a suitable tool. After selection it appears "
            "as a chip in the node tool list."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    tools = persisted["nodes"]["agent"].get("tools") or []
    assert len(tools) >= 1, f"expected at least one tool, got {tools!r}"
    await scenario.step(
        "Опубликуйте агента с инструментом",
        page,
        screenshot_name="agent-tools-published",
        label_en="Publish the agent with the tool",
        details=(
            "**Демонстрация результата.** Нажмите «Опубликовать» — инструмент остаётся "
            "в списке ноды, а сохранённая версия агента содержит подключённый tool.\n\n"
            "**Итог.** Теперь вы умеете включать режим инструментов, выбирать tool из "
            "библиотеки и публиковать рабочую версию агента."
        ),
        details_en=(
            "**Result demonstration.** Click Publish — the tool stays in the node list "
            "and the saved agent version includes the attached tool.\n\n"
            "**Summary.** You can enable tools mode, pick a tool from the library, "
            "and publish a working agent version."
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
    await flows_open_node_editor(page, "agent")
    await scenario.step(
        "Откройте настройки агента",
        page,
        screenshot_name="structured-editor-opened",
        label_en="Open agent settings",
        details=(
            "В редакторе ноды найдите блок «Режим вывода». Именно он определяет, "
            "будет ли ответ обычным текстом или строгим JSON."
        ),
        details_en=(
            "In the node editor find the Output mode block. It decides whether the "
            "reply is plain text or strict JSON."
        ),
    )

    await flows_click_llm_output_mode(page, "structured")
    schema_editor = page.locator("flows-llm-node-editor platform-json-editor").first
    await expect(schema_editor).to_be_visible(timeout=15_000)
    await scenario.step(
        "Включите структурированный вывод",
        page,
        screenshot_name="structured-mode-enabled",
        label_en="Enable structured output",
        details=(
            "Переключите режим на «Структурированный». Появится редактор JSON-схемы — "
            "в нём задаются поля, которые агент обязан вернуть."
        ),
        details_en=(
            "Switch the mode to Structured. A JSON schema editor appears where you "
            "define the fields the agent must return."
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
            "**Итог.** Теперь вы умеете включать structured output и задавать схему ответа "
            "для автоматической обработки данных заказа."
        ),
        details_en=(
            "**Result demonstration.** After publishing, structured output mode and the "
            "JSON schema are saved on the agent and visible when you reopen the node.\n\n"
            "**Summary.** You can enable structured output and define a response schema "
            "for automatic order data processing."
        ),
    )

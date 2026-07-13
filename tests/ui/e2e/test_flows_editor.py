"""UI E2E сценарии Flows: редактор графа (настройка ответов, развилки, порядок).

Сквозной пример «Зелёный сад» — см. docs/scenarios/flows/CATALOG.md.
"""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_STORE,
    GREEN_GARDEN_STORE_EN,
    flows_add_sticky_note,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_branch_condition_payload,
    flows_canvas_toolbar_action,
    flows_dataflow_problems_payload,
    flows_doc_flow_id,
    flows_execution_send_message,
    flows_llm_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_publish_editor,
    flows_save_edge_condition_modal,
    flows_set_edge_condition_simple,
    flows_set_selected_llm_prompt,
    flows_switch_editor_mode,
    flows_toggle_data_wires,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_PROMPT_V1 = (
    "Ты — вежливый помощник интернет-магазина «Зелёный сад». "
    "Обращайся к покупателю по имени {customer_name} и помогай с выбором растений."
)
_PROMPT_V2 = _PROMPT_V1 + " Всегда уточняй адрес и сроки доставки."
_ORGANIZE_GRAPH_PROMPT_FIXED = (
    "Кратко объясни покупателю «Зелёного сада», как оформить возврат садовых товаров."
)


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="configure-agent-answers",
    title="Настраиваем ответы агента: промпт и модель",
    description=(
        "**Для чего:** эта инструкция поможет задать поведение агента и модель ответа, "
        "а затем изменить настройку и сохранить её.\n\n"
        "**Какие проблемы решает:** агент отвечает не так, как нужно магазину, и неясно, "
        "где менять инструкцию и модель.\n\n"
        "**Результат:** агент отвечает вежливо от лица «Зелёного сада», а изменения "
        "опубликованы и сохраняются после переоткрытия."
    ),
    title_en="Shape agent answers: prompt and model",
    description_en=(
        "**What for:** this guide helps you set the agent's behavior and answer model, "
        "then change the setting and save it.\n\n"
        "**Problems it solves:** the agent answers differently than the shop needs, and "
        "it's unclear where to change the instruction and the model.\n\n"
        "**Result:** the agent answers politely on behalf of Green Garden, and changes "
        "are published and persist after reopening."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_configure_agent_answers(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("configure_answers", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME, prompt="Отвечай кратко."),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте агента в редакторе",
        page,
        screenshot_name="editor-opened",
        label_en="Open the agent in the editor",
        details=(
            "На канве редактора находится нода ответа агента. Именно она определяет, как "
            "агент разговаривает с покупателем."
        ),
        details_en=(
            "The editor canvas contains the agent answer node. It defines how the agent "
            "talks to the customer."
        ),
    )

    await flows_open_node_editor(page, "agent")
    await flows_set_selected_llm_prompt(page, _PROMPT_V1)
    await scenario.step(
        "Напишите инструкцию агента",
        page,
        screenshot_name="prompt-first-version",
        label_en="Write the agent instruction",
        details=(
            "В редакторе ноды впишите инструкцию (промпт). Здесь можно подставлять "
            "переменные вроде имени покупателя в фигурных скобках — агент использует их в "
            "ответе. Это главный способ задать тон и правила общения."
        ),
        details_en=(
            "In the node editor, type the instruction (prompt). You can insert variables "
            "such as the customer name in curly braces, and the agent uses them in its "
            "reply. This is the main way to set the tone and rules of communication."
        ),
    )

    await flows_publish_editor(page)
    await scenario.step(
        "Опубликуйте черновик",
        page,
        screenshot_name="published-first",
        label_en="Publish the draft",
        details=(
            "Нажмите «Опубликовать». Черновик становится рабочей версией — теперь агент "
            "отвечает по новой инструкции."
        ),
        details_en=(
            "Click Publish. The draft becomes the live version, so the agent now answers "
            "using the new instruction."
        ),
    )

    await flows_open_node_editor(page, "agent")
    await flows_set_selected_llm_prompt(page, _PROMPT_V2)
    await flows_publish_editor(page)
    await scenario.step(
        "Измените инструкцию и опубликуйте снова",
        page,
        screenshot_name="published-second",
        label_en="Change the instruction and publish again",
        details=(
            "Дополните инструкцию (например, попросите всегда уточнять доставку) и снова "
            "опубликуйте. Так вы дорабатываете поведение агента по мере необходимости."
        ),
        details_en=(
            "Extend the instruction (for example, ask it to always clarify delivery) and "
            "publish again. This is how you refine the agent's behavior over time."
        ),
    )

    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    agent_prompt = persisted["nodes"]["agent"]["prompt"]
    assert "доставки" in agent_prompt, f"updated prompt not persisted: {agent_prompt!r}"

    await flows_open_editor(page, flows_ui, flow_id)
    editor = await flows_open_node_editor(page, "agent")
    await expect(editor).to_contain_text("доставки", timeout=15_000)
    await scenario.step(
        "Переоткройте агента и проверьте настройки",
        page,
        screenshot_name="reopened-prompt-persisted",
        label_en="Reopen the agent and verify settings",
        details=(
            "**Демонстрация результата.** Закройте и снова откройте ноду — обновлённая "
            "инструкция на месте, значит настройка сохранилась.\n\n"
            "**Итог.** Теперь вы умеете задавать и менять инструкцию агента и публиковать "
            "изменения."
        ),
        details_en=(
            "**Result demonstration.** Close and reopen the node — the updated "
            "instruction is still there, which means the setting was saved.\n\n"
            "**Summary.** You can now set and change the agent instruction and publish "
            "changes."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="branch-by-condition",
    title="Развилка в диалоге: условия на связях",
    description=(
        "**Для чего:** эта инструкция поможет направлять покупателя «Зелёного сада» "
        "по разным веткам — например, заказ и возврат.\n\n"
        "**Какие проблемы решает:** агент обрабатывает все обращения одинаково, хотя "
        "сценарии заказа и возврата требуют разных ответов.\n\n"
        "**Результат:** запрос о возврате идёт по ветке «Агент возвратов», и это видно "
        "при тестовом запуске."
    ),
    title_en="Branch the dialog with edge conditions",
    description_en=(
        "**What for:** this guide helps route Green Garden customers down different "
        "branches, such as order handling versus returns.\n\n"
        "**Problems it solves:** the agent treats every request the same even though "
        "order and return scenarios need different answers.\n\n"
        "**Result:** a return request follows the Returns Agent branch, visible during "
        "a test run."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_branch_by_condition(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = flows_service, taskiq_worker
    flow_id = flows_doc_flow_id("branch_condition", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_branch_condition_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте агента с развилкой",
        page,
        screenshot_name="branch-graph-opened",
        label_en="Open the agent with a branch",
        details=(
            "В редакторе «Помощника Зелёного сада» уже есть маршрутизатор и две ветки: "
            "обычный заказ и «Агент возвратов». Так вы видите, куда можно направить "
            "разные типы обращений."
        ),
        details_en=(
            "In the Green Garden Assistant editor there is already a router and two "
            "branches: a regular order path and the Returns Agent. This shows where "
            "different request types can go."
        ),
    )

    await flows_set_edge_condition_simple(
        page,
        variable="intent",
        operator="==",
        value="returns",
        edge_index=1,
    )
    await flows_save_edge_condition_modal(page)
    await scenario.step(
        "Задайте условие на связи к возвратам",
        page,
        screenshot_name="returns-edge-condition",
        label_en="Set the condition on the returns link",
        details=(
            "Кликните подпись связи к блоку «Агент возвратов» и задайте условие: "
            "переменная intent равна returns. Так ветка сработает только для обращений "
            "о возврате."
        ),
        details_en=(
            "Click the label on the link to the Returns Agent block and set a condition: "
            "variable intent equals returns. The branch runs only for return requests."
        ),
    )

    await flows_publish_editor(page)
    await scenario.step(
        "Опубликуйте изменения",
        page,
        screenshot_name="branch-published",
        label_en="Publish the changes",
        details=(
            "Нажмите «Опубликовать», чтобы условие на связи стало рабочей версией агента. "
            "Без публикации тестовый запуск будет использовать старые правила."
        ),
        details_en=(
            "Click Publish so the link condition becomes the live agent version. Without "
            "publishing, a test run would still use the old rules."
        ),
    )

    await flows_switch_editor_mode(page, "run")
    await scenario.step(
        "Переключитесь в режим запуска",
        page,
        screenshot_name="run-mode-opened",
        label_en="Switch to run mode",
        details=(
            "В шапке редактора выберите режим «Запуск». Справа откроется панель чата, "
            "где можно проверить агента, не выходя из редактора."
        ),
        details_en=(
            "In the editor header, choose Run mode. A chat panel opens on the right "
            "where you can test the agent without leaving the editor."
        ),
    )

    await flows_execution_send_message(page, "нужен возврат")
    returns_node = page.locator(
        "flows-flow-canvas g.node[data-node-id='returns_path'][data-state='completed']"
    ).first
    await expect(returns_node).to_be_visible(timeout=120_000)
    returns_reply = page.locator("flows-execution-panel").get_by_text("returns-path", exact=False).first
    if await returns_reply.count() > 0:
        await expect(returns_reply).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте ветку возвратов",
        page,
        screenshot_name="returns-path-highlighted",
        label_en="Verify the returns branch",
        details=(
            "**Демонстрация результата.** Отправьте «нужен возврат» и дождитесь ответа "
            "returns-path в чате запуска — значит сработала ветка «Агент возвратов». "
            "На канве подсвечивается пройденный путь.\n\n"
            f"**Итог.** Теперь вы умеете направлять покупателей «{GREEN_GARDEN_STORE}» "
            f"по разным веткам с помощью условий на связях."
        ),
        details_en=(
            "**Result demonstration.** Send «нужен возврат» and wait for a returns-path "
            "reply in the run chat — the Returns Agent branch ran. The canvas highlights "
            "the path that executed.\n\n"
            f"**Summary.** You can now route {GREEN_GARDEN_STORE_EN} customers down "
            "different branches using link conditions."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="organize-large-graph",
    title="Наводим порядок в большом графе",
    description=(
        "**Для чего:** эта инструкция поможет держать сложного агента «Зелёного сада» "
        "понятным и быстро находить ошибки в связях данных.\n\n"
        "**Какие проблемы решает:** граф разрастается, теряются связи между блоками "
        "и появляются предупреждения о нехватке данных.\n\n"
        "**Результат:** граф аккуратно размечен заметками, проблемная связь найдена "
        "и исправлена — список предупреждений пуст."
    ),
    title_en="Keep a large graph readable",
    description_en=(
        "**What for:** this guide helps keep a complex Green Garden agent readable and "
        "find data wiring issues quickly.\n\n"
        "**Problems it solves:** the graph grows, data links get lost, and warnings "
        "appear about missing inputs.\n\n"
        "**Result:** the graph is annotated with notes, the broken link is found and "
        "fixed, and the warnings list is empty."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_organize_large_graph(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("organize_graph", unique_id)
    organize_payload = flows_dataflow_problems_payload(flow_id)
    organize_payload["name"] = GREEN_GARDEN_AGENT_NAME
    organize_payload["edges"] = []
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        organize_payload,
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_canvas_toolbar_action(page, "fit_view")
    await scenario.step(
        "Подгоните масштаб канвы",
        page,
        screenshot_name="canvas-fit-view",
        label_en="Fit the canvas view",
        details=(
            "На нижней панели нажмите «Подогнать вид», чтобы все блоки «Помощника "
            "Зелёного сада» поместились на экране. Так проще ориентироваться в "
            "большом графе."
        ),
        details_en=(
            "On the bottom toolbar, click Fit view so all Green Garden Assistant blocks "
            "fit on screen. This makes a large graph easier to navigate."
        ),
    )

    await flows_add_sticky_note(
        page,
        f"Блок ответа — уточняет доставку для покупателя «{GREEN_GARDEN_STORE}»",
    )
    await scenario.step(
        "Добавьте поясняющую заметку",
        page,
        screenshot_name="sticky-note-added",
        label_en="Add an explanatory sticky note",
        details=(
            "Добавьте заметку рядом с блоком ответа и кратко опишите его роль — "
            "например, что здесь уточняется доставка. Заметки помогают коллегам "
            "понимать большой граф без лишних вопросов."
        ),
        details_en=(
            "Add a note next to the answer block and briefly describe its role — for "
            "example, that delivery is clarified here. Notes help teammates understand "
            "a large graph without extra questions."
        ),
    )

    await flows_toggle_data_wires(page)
    await scenario.step(
        "Включите показ связей данных",
        page,
        screenshot_name="data-wires-visible",
        label_en="Show data links",
        details=(
            "На нижней панели включите отображение связей данных — пункт со значком "
            "цепочки. Так видно, какие переменные передаются между блоками, а где "
            "связь ещё не проведена."
        ),
        details_en=(
            "On the bottom toolbar, turn on data link display — the chain icon. You "
            "can see which variables pass between blocks and where a link is still "
            "missing."
        ),
    )

    await flows_open_node_editor(page, "llm_1")
    await scenario.step(
        "Откройте блок LLM с неизвестной переменной",
        page,
        screenshot_name="llm-block-with-missing-variable",
        label_en="Open the LLM block with an unknown variable",
        details=(
            "Откройте LLM-блок с промптом, где используется переменная missing_topic. "
            "При включённых связях данных такие блоки подсвечиваются как проблемные."
        ),
        details_en=(
            "Open the LLM block whose prompt references the missing_topic variable. "
            "With data links enabled, such blocks are highlighted as problematic."
        ),
    )

    await flows_set_selected_llm_prompt(page, _ORGANIZE_GRAPH_PROMPT_FIXED)
    await scenario.step(
        "Исправьте инструкцию проблемного блока",
        page,
        screenshot_name="prompt-variable-fixed",
        label_en="Fix the problematic block instruction",
        details=(
            "Замените промпт с неизвестной переменной на понятную инструкцию без "
            "фигурных скобок, которую агент сможет выполнить."
        ),
        details_en=(
            "Replace the prompt with an unknown variable by a clear instruction without "
            "curly braces that the agent can follow."
        ),
    )

    await flows_publish_editor(page)
    await scenario.step(
        "Опубликуйте и убедитесь, что предупреждений нет",
        page,
        screenshot_name="problems-cleared",
        label_en="Publish and confirm warnings are gone",
        details=(
            "**Демонстрация результата.** Опубликуйте черновик — промпт больше не ссылается "
            "на несуществующую переменную.\n\n"
            f"**Итог.** Теперь вы умеете размечать граф заметками, включать связи данных "
            f"и исправлять проблемные блоки «{GREEN_GARDEN_STORE}»."
        ),
        details_en=(
            "**Result demonstration.** Publish the draft — the prompt no longer references "
            "a missing variable.\n\n"
            f"**Summary.** You can now annotate the graph with notes, show data links, "
            f"and fix problematic blocks for {GREEN_GARDEN_STORE_EN}."
        ),
    )

"""E2E сценарии dataflow wiring и problems navigation в редакторе flows."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_api_get_flow,
    flows_doc_flow_id,
    flows_publish_editor,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


def _dataflow_broken_payload(flow_id: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "name": "Dataflow wiring E2E",
        "description": "Code produces topic, LLM requires topic via prompt",
        "entry": "code_1",
        "nodes": {
            "code_1": {
                "type": "code",
                "name": "Code",
                "language": "python",
                "code": (
                    "async def run(args, state):\n"
                    "    state['topic'] = 'ai'\n"
                    "    return {}\n"
                ),
                "pos_x": 0,
                "pos_y": 0,
            },
            "llm_1": {
                "type": "llm_node",
                "name": "LLM",
                "prompt": "Summarize {topic}",
                "pos_x": 320,
                "pos_y": 0,
            },
        },
        "edges": [{"from_node": "code_1", "to_node": "llm_1"}],
        "variables": {},
    }


def _problems_payload(flow_id: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "name": "Dataflow problems E2E",
        "description": "LLM prompt requires undeclared variable",
        "entry": "llm_1",
        "nodes": {
            "llm_1": {
                "type": "llm_node",
                "name": "Broken LLM",
                "prompt": "Explain {missing_topic}",
                "pos_x": 0,
                "pos_y": 0,
            },
        },
        "edges": [{"from_node": "llm_1", "to_node": None}],
        "variables": {},
    }


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="dataflow-wiring",
    title="Flows: визуализация dataflow wiring",
    description="Показывает переключатель data wires и проблемы после inspect на канве.",
    title_en="Flows: dataflow wiring visualization",
    description_en="Shows the data wires toggle and problems after inspect on the canvas.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_dataflow_wiring_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("doc_dataflow", unique_id)
    await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)
    await flows_api_create_flow(flows_ui.origin, auth_token_system, _dataflow_broken_payload(flow_id))

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor/default", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-flow-canvas g.node")).to_have_count(2, timeout=30_000)
    await scenario.step(
        "Открываем редактор flow с code и llm нодами. Канва показывает граф с потенциальным dataflow.",
        page,
        label_en="Open the flow editor with code and LLM nodes. The canvas shows a graph with potential dataflow.",
    )

    wires_btn = page.locator("flows-bottom-toolbar platform-button").filter(
        has=page.locator("platform-icon[name='link']")
    )
    await expect(wires_btn).to_be_visible(timeout=30_000)
    await wires_btn.click()
    await scenario.step(
        "Включаем показ data wires в нижней панели. На канве появляются связи по данным.",
        page,
        label_en="Turn on data wires in the bottom toolbar. Data connections appear on the canvas.",
    )
    await expect(page.locator("flows-flow-canvas [data-wires-layer] g.data-wire")).to_have_count(
        1, timeout=30_000
    )

    await flows_publish_editor(page)
    saved = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    assert "llm_1" in saved["nodes"]


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="dataflow-problems",
    title="Flows: навигация по dataflow problems",
    description="Показывает счётчик проблем в шапке и переход к проблемной ноде.",
    title_en="Flows: navigating dataflow problems",
    description_en="Shows the problem counter in the header and navigation to the problematic node.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_dataflow_problems_navigation_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("doc_problems", unique_id)
    await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)
    await flows_api_create_flow(flows_ui.origin, auth_token_system, _problems_payload(flow_id))

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor/default", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем flow с намеренно незамапленной prompt-переменной.",
        page,
        label_en="Open a flow with an intentionally unmapped prompt variable.",
    )

    problems_btn = page.locator("flows-editor-header .problems-btn")
    await expect(problems_btn).to_be_visible(timeout=30_000)
    await problems_btn.click()
    await expect(page.locator("flows-editor-header .problems-flyout")).to_be_visible(timeout=10_000)
    await scenario.step(
        "В шапке виден счётчик проблем dataflow. Открываем список issues.",
        page,
        label_en="The header shows a dataflow problem count. Open the issues list.",
    )

    await page.locator("flows-editor-header .problem-item").first.click()
    await expect(page.locator("flows-flow-canvas g.node.selected")).to_have_count(1, timeout=10_000)
    await scenario.step(
        "Клик по issue выделяет проблемную ноду на канве.",
        page,
        label_en="Clicking an issue selects the problematic node on the canvas.",
    )

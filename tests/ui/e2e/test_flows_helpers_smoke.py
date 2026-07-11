"""Smoke-тест фундамента canvas-хелперов (без scenario-маркера).

Гейт готовности: drop ноды + wiring порт→порт + publish + read-back через API.
"""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_api_get_flow,
    flows_branch_condition_payload,
    flows_canvas_node_ids,
    flows_doc_flow_id,
    flows_drop_node,
    flows_graph_payload,
    flows_open_edge_condition_modal,
    flows_open_editor,
    flows_publish_editor,
    flows_save_edge_condition_modal,
    flows_set_edge_condition_simple,
    flows_switch_editor_mode,
    flows_wire_ports,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_canvas_wiring_smoke(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("wire_smoke", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name="Wire Smoke"),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)

    await flows_drop_node(page, "llm_node", x=520, y=320)
    node_ids = await flows_canvas_node_ids(page)
    new_nodes = [n for n in node_ids if n not in {"start", "end"}]
    assert new_nodes, "LLM node was not added to the canvas"
    llm_id = new_nodes[0]

    await flows_wire_ports(page, "start", llm_id)
    await flows_wire_ports(page, llm_id, "end")

    await flows_publish_editor(page)
    await expect(page.locator("flows-editor-header")).to_be_visible(timeout=15_000)

    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    edges = persisted.get("edges") or []
    pairs = {(e.get("from_node"), e.get("to_node")) for e in edges}
    assert ("start", llm_id) in pairs, f"edge start->{llm_id} missing in {pairs}"
    assert (llm_id, "end") in pairs, f"edge {llm_id}->end missing in {pairs}"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_edge_condition_and_run_mode_smoke(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("edge_smoke", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_branch_condition_payload(flow_id, name="Edge Smoke"),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_set_edge_condition_simple(
        page,
        variable="intent",
        operator="==",
        value="returns",
        edge_index=1,
    )
    await flows_save_edge_condition_modal(page)
    await flows_publish_editor(page)

    await flows_switch_editor_mode(page, "run")
    await expect(page.locator("flows-execution-panel platform-chat")).to_be_visible(timeout=15_000)

    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    edges = persisted.get("edges") or []
    returns_edge = next((e for e in edges if e.get("to_node") == "returns_path"), None)
    assert returns_edge is not None
    condition = returns_edge.get("condition") or {}
    assert condition.get("value") == "returns"


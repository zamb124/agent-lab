"""Playwright E2E: Interface editor workspace opens with toolbar, canvas, problems and switches modes."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    INTERFACE_PAGE_TAB_SELECTOR,
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_doc_flow_id,
    flows_graph_payload,
    flows_interface_canvas_block,
    flows_open_interface_editor_workspace,
    flows_switch_editor_workspace,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def flows_editor_browser_stack_ready(flows_service, taskiq_worker):
    _ = flows_service, taskiq_worker
    yield


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_interface_editor_opens_with_canvas_and_problems(
    flows_editor_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_editor_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("iface_editor", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=f"Interface Editor {unique_id}"),
    )
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        editor = page.locator("flows-interface-editor").first
        await expect(editor).to_be_visible(timeout=30_000)
        toolbar = editor.locator("flows-interface-toolbar")
        await expect(toolbar).to_be_visible(timeout=30_000)
        await expect(
            toolbar.get_by_role("button", name=re.compile(r"^\s*(Undo|Отменить)\s*$"))
        ).to_be_visible(timeout=10_000)
        await expect(
            toolbar.get_by_role("button", name=re.compile(r"^\s*(Redo|Повторить)\s*$"))
        ).to_be_visible(timeout=10_000)
        await expect(toolbar.locator(".status")).to_have_attribute("data-dirty", "false")
        await expect(toolbar.locator(".status")).to_have_attribute("data-errors", "false")
        await expect(editor.locator(INTERFACE_PAGE_TAB_SELECTOR)).to_have_count(1, timeout=30_000)
        await expect(editor.locator("flows-interface-add-panel").first).to_be_visible(timeout=30_000)
        # Шаблон чата по умолчанию рендерится тем же <platform-flow-ui>, что и runtime.
        canvas = editor.locator(".canvas platform-flow-ui[editing]").first
        await expect(canvas).to_be_visible(timeout=30_000)
        await expect(flows_interface_canvas_block(page, "conversation")).to_have_count(1, timeout=30_000)
        await expect(flows_interface_canvas_block(page, "agent_identity")).to_have_count(1, timeout=30_000)
        await expect(editor.locator(".problems .ok")).to_be_visible(timeout=30_000)

        await flows_switch_editor_workspace(page, "logic")
        await expect(page.locator("flows-flow-canvas").first).to_be_visible(timeout=30_000)
        await expect(page.locator("flows-interface-editor")).to_have_count(0)

        await flows_switch_editor_workspace(page, "run")
        await expect(page.locator("flow-editor-page platform-flow-ui").first).to_be_visible(
            timeout=30_000
        )
        await expect(page.locator("flows-interface-editor")).to_have_count(0)

        await flows_switch_editor_workspace(page, "interface")
        await expect(page.locator("flows-interface-editor").first).to_be_visible(timeout=30_000)
        await expect(
            page.locator("flows-editor-header .row-center platform-segmented-control")
            .get_by_label("Interface", exact=True)
        ).to_have_attribute("data-active", "true", timeout=10_000)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

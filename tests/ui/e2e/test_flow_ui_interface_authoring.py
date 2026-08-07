"""Playwright E2E: dense Interface editor authoring (plan §25.8 / §25.9)."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_doc_flow_id,
    flows_graph_payload,
    flows_open_interface_editor_workspace,
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
async def test_flow_ui_interface_palette_adds_textfield_to_layers(
    flows_editor_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_editor_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("iface_palette", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=f"Interface Palette {unique_id}"),
    )
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        editor = page.locator("flows-interface-editor").first
        await expect(editor).to_be_visible(timeout=30_000)

        palette = editor.locator("flows-interface-palette").first
        await expect(palette).to_be_visible(timeout=30_000)
        add_field = palette.locator("button").filter(has_text=re.compile(r"^TextField$")).first
        await expect(add_field).to_be_visible(timeout=10_000)
        await add_field.click()

        layers = editor.locator("flows-interface-layers-tree").first
        await expect(layers.get_by_text("TextField", exact=False).first).to_be_visible(
            timeout=15_000
        )
        await expect(editor.locator("flows-interface-canvas").first).to_be_visible(
            timeout=15_000
        )
        await expect(
            editor.locator("flows-interface-toolbar .badge").first
        ).to_be_attached(timeout=30_000)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_interface_editor_undo_redo_after_palette_add(
    flows_editor_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_editor_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("iface_undo", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=f"Interface Undo {unique_id}"),
    )
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        editor = page.locator("flows-interface-editor").first
        layers = editor.locator("flows-interface-layers-tree").first
        before = await layers.locator("button").count()

        await editor.locator("flows-interface-palette button").filter(
            has_text=re.compile(r"^Badge$")
        ).first.click()
        await expect(layers.get_by_text("Badge", exact=False).first).to_be_visible(
            timeout=15_000
        )
        after_add = await layers.locator("button").count()
        assert after_add > before

        toolbar = editor.locator("flows-interface-toolbar")
        undo = toolbar.get_by_role(
            "button", name=re.compile(r"^\s*(Undo|Отменить)\s*$")
        ).first
        await undo.click()
        await expect(layers.get_by_text("Badge", exact=False)).to_have_count(0, timeout=15_000)

        redo = toolbar.get_by_role(
            "button", name=re.compile(r"^\s*(Redo|Повторить)\s*$")
        ).first
        await redo.click()
        await expect(layers.get_by_text("Badge", exact=False).first).to_be_visible(
            timeout=15_000
        )
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

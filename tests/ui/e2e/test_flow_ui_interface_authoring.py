"""Playwright E2E: Interface editor authoring — add panel, canvas selection, undo/redo, properties."""

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
    flows_interface_add_block,
    flows_interface_canvas_block,
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
async def test_flow_ui_interface_add_panel_inserts_text_input_and_selects_it(
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
        await expect(flows_interface_canvas_block(page, "text_input")).to_have_count(0)

        await flows_interface_add_block(page, "Text input")

        inserted = flows_interface_canvas_block(page, "text_input")
        await expect(inserted).to_have_count(1, timeout=15_000)
        properties = editor.locator("flows-interface-properties-panel").first
        await expect(properties).to_be_visible(timeout=15_000)
        await expect(properties.locator(".head .type")).to_have_text(
            re.compile(r"Text input|Текстовое поле"), timeout=10_000
        )
        block_id = await inserted.get_attribute("data-block-id")
        assert isinstance(block_id, str) and block_id != ""
        await expect(editor.locator(".selection")).to_be_visible(timeout=10_000)
        # Поле без действия на странице — предупреждение no_action в списке проблем.
        await expect(editor.locator(".problems .problem")).to_have_count(1, timeout=15_000)
        await expect(editor.locator("flows-interface-toolbar .status")).to_have_attribute(
            "data-dirty", "true", timeout=10_000
        )
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_interface_editor_undo_redo_after_add(
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
        badges = flows_interface_canvas_block(page, "badge")
        await expect(badges).to_have_count(0)

        await flows_interface_add_block(page, "Badge")
        await expect(badges).to_have_count(1, timeout=15_000)

        toolbar = editor.locator("flows-interface-toolbar")
        undo = toolbar.get_by_role("button", name=re.compile(r"^\s*(Undo|Отменить)\s*$")).first
        await expect(undo).to_be_enabled(timeout=10_000)
        await undo.click()
        await expect(badges).to_have_count(0, timeout=15_000)

        redo = toolbar.get_by_role("button", name=re.compile(r"^\s*(Redo|Повторить)\s*$")).first
        await expect(redo).to_be_enabled(timeout=10_000)
        await redo.click()
        await expect(badges).to_have_count(1, timeout=15_000)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_interface_agent_card_properties_expose_image_url(
    flows_editor_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_editor_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("iface_agent_img", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=f"Interface Agent Image {unique_id}"),
    )
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        editor = page.locator("flows-interface-editor").first
        await expect(editor).to_be_visible(timeout=30_000)
        identity = flows_interface_canvas_block(page, "agent_identity").first
        await expect(identity).to_be_visible(timeout=15_000)
        await identity.click()

        properties = editor.locator("flows-interface-properties-panel").first
        await expect(properties).to_be_visible(timeout=10_000)
        await expect(properties.locator(".head .type")).to_have_text(
            re.compile(r"Agent card|Карточка агента"), timeout=10_000
        )
        image_field = properties.locator("platform-field").filter(
            has_text=re.compile(r"^\s*(Image|Изображение)\s*$")
        )
        await expect(image_field.first).to_be_visible(timeout=10_000)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

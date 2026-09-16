"""UI E2E: инспектор ноды code_agent."""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, Response, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_doc_flow_id,
    flows_drop_node,
    flows_graph_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_set_platform_field,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_CHEETAH_GIT = "https://github.com/zub123123123/cheetah-agent"
_CHEETAH_SHA = "70eb6c3c6909d1f975d9c7e6c723bae5db897478"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_code_agent_inspector(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    office_service: object,
    flows_service: object,
) -> None:
    _ = office_service, flows_service
    flow_id = flows_doc_flow_id("code_agent_inspector", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name="Code agent inspector"),
    )
    page = ui_page_system
    code_agent_404: list[str] = []

    def _on_response(response: Response) -> None:
        if "/code-agent" in response.url and response.status == 404:
            code_agent_404.append(f"{response.status} {response.url}")

    page.on("response", _on_response)
    await flows_open_editor(page, flows_ui, flow_id)
    node_id = await flows_drop_node(page, "code_agent", x=520, y=320)
    if not node_id:
        raise AssertionError("code_agent node was not added to the canvas")
    await flows_open_node_editor(page, node_id)
    editor = page.locator("flows-code-agent-editor").first
    await expect(editor).to_be_visible(timeout=15_000)
    await expect(page.get_by_test_id("code-agent-rebuild")).to_be_visible()
    await expect(page.get_by_test_id("code-agent-logs")).to_be_visible()
    await expect(page.get_by_test_id("code-agent-import-git")).to_be_visible()
    await expect(page.get_by_test_id("code-agent-dropzone")).to_be_visible()
    argv_field = page.get_by_test_id("code-agent-argv")
    await expect(argv_field).to_be_visible()
    argv_hint = await argv_field.evaluate("(el) => el.hint")
    if not isinstance(argv_hint, str) or "python3" not in argv_hint:
        raise AssertionError(f"code-agent argv hint must mention python3, got {argv_hint!r}")
    argv_value = await argv_field.evaluate("(el) => el.value")
    if argv_value not in ("", None):
        raise AssertionError(f"code-agent argv must start empty, got {argv_value!r}")
    await expect(editor.locator("a.open-docs")).to_be_visible(timeout=30_000)
    href = await editor.locator("a.open-docs").get_attribute("href")
    if href is None or "catalog_id=" not in href:
        raise AssertionError(f"Documents catalog_id missing in href: {href!r}")
    if "namespace=" not in href:
        raise AssertionError(f"Documents namespace missing in href: {href!r}")
    if code_agent_404:
        raise AssertionError(f"code-agent 404 after drop: {code_agent_404}")

    url_field = page.get_by_test_id("code-agent-git-url")
    await flows_set_platform_field(url_field, _CHEETAH_GIT)
    sha_field = page.get_by_test_id("code-agent-source-sha")
    await expect(sha_field).to_be_visible()
    await flows_set_platform_field(sha_field, _CHEETAH_SHA)
    await page.get_by_test_id("code-agent-import-git").click()
    await expect(editor.locator(".tree")).to_contain_text("main.py", timeout=120_000)
    if code_agent_404:
        raise AssertionError(f"code-agent 404 after git import: {code_agent_404}")

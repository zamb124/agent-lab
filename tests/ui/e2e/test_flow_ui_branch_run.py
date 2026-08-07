"""Playwright E2E: a branch keeps running its own branch.

The branch reaches the runtime only through A2A `params.metadata.branch`, so the
test reads the actual requests the browser sends. It also pins the session URL:
once a session starts, the branch must stay in the address, otherwise a reload or
"New screen" silently falls back to the base flow.
"""

import json
import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_branch,
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_chat_echo_payload,
    flows_chat_wait_ready,
    flows_doc_flow_id,
    flows_open_chat_page,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


def _collect_a2a_branches(page: Page, flow_id: str) -> list[str | None]:
    """Branch metadata of every A2A SendMessage the page issues for this flow."""
    branches: list[str | None] = []

    def on_request(request) -> None:
        if request.method != "POST" or f"/flows/api/v1/{flow_id}" not in request.url:
            return
        body = request.post_data
        if not body:
            return
        try:
            payload = json.loads(body)
        except ValueError:
            return
        if not isinstance(payload, dict) or "SendMessage" not in str(payload.get("method")):
            return
        params = payload.get("params")
        metadata = params.get("metadata") if isinstance(params, dict) else None
        branches.append(metadata.get("branch") if isinstance(metadata, dict) else None)

    page.on("request", on_request)
    return branches


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_branch_chat_bootstraps_and_keeps_its_branch(
    flows_service,
    taskiq_worker,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_service, taskiq_worker
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("branch_chat", unique_id)
    branch_id = f"crm_{unique_id}"
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_chat_echo_payload(flow_id, name=f"Branch chat {unique_id}"),
    )
    try:
        await flows_api_create_branch(
            flows_ui.origin,
            auth_token_system,
            flow_id,
            branch_id=branch_id,
            name="CRM",
        )
        branches = _collect_a2a_branches(page, flow_id)
        await flows_open_chat_page(page, flows_ui, flow_id, branch_id=branch_id)
        await flows_chat_wait_ready(page)

        assert branches, "branch chat issued no A2A SendMessage"
        assert set(branches) == {branch_id}, (
            f"branch chat bootstrapped {branches!r} instead of {branch_id!r}"
        )

        # The session URL keeps the branch, so reload and New screen stay on it.
        await expect(page).to_have_url(
            re.compile(rf"/flows/{re.escape(flow_id)}/branch/{re.escape(branch_id)}/session/"),
            timeout=30_000,
        )

        branches.clear()
        await page.reload(wait_until="domcontentloaded")
        await expect(page.locator("chat-page platform-flow-ui")).to_be_visible(timeout=30_000)
        await flows_chat_wait_ready(page)
        assert branches, "reload issued no A2A SendMessage"
        assert set(branches) == {branch_id}, (
            f"reload bootstrapped {branches!r} instead of {branch_id!r}"
        )
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

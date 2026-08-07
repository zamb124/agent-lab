"""Dense Flow UI continuity E2E without mocks (plan §25.4.1)."""

from __future__ import annotations

import os
import re
from urllib.parse import unquote

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_chat_test_flow,
    flows_api_delete_flow,
    flows_chat_create_share,
    flows_chat_draft_value,
    flows_chat_fill_draft,
    flows_chat_session_url,
    flows_chat_wait_ready,
    flows_chat_wait_saved,
    flows_dismiss_pwa_install_banner,
    flows_doc_flow_id,
    flows_interface_add_page,
    flows_open_chat_page,
    flows_open_interface_editor_workspace,
    flows_publish_editor,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def flows_dense_browser_stack_ready(flows_service, frontend_service, taskiq_worker):
    _ = flows_service, frontend_service, taskiq_worker
    yield


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_autosync_does_not_invoke_flow(
    flows_dense_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_dense_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"nosubmit-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)

    await expect(page.get_by_text(re.compile(rf"chat-ok:{re.escape(draft)}"))).to_have_count(0)
    await page.reload(wait_until="domcontentloaded")
    await flows_chat_wait_ready(page)
    assert await flows_chat_draft_value(page) == draft
    await expect(page.get_by_text(re.compile(r"^chat-ok:"))).to_have_count(0)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_viewer_cannot_submit(
    flows_dense_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_dense_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"view-block-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    share = await flows_chat_create_share(page, permission="view")
    code = share.share_url.rstrip("/").split("/l/")[-1]

    viewer = await page.context.new_page()
    viewer.set_default_timeout(45_000)
    try:
        await viewer.goto(
            f"{frontend_ui.origin}/l/{code}",
            wait_until="domcontentloaded",
        )
        await viewer.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
        surface = viewer.locator("platform-flow-ui").first
        await expect(surface).to_be_visible(timeout=60_000)
        textarea = surface.locator(
            '[data-flow-ui-component="message-input"] textarea, textarea'
        ).first
        await expect(textarea).to_have_attribute("readonly", "", timeout=30_000)
        submit = surface.get_by_role(
            "button", name=re.compile(r"^(Submit|Отправить|Send)$")
        ).first
        await expect(submit).to_be_disabled(timeout=15_000)
        await expect(surface.get_by_text(re.compile(r"^chat-ok:"))).to_have_count(0)
    finally:
        await viewer.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_owner_collaborator_occ_conflict_surfaces(
    flows_dense_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_dense_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    seed = f"occ-seed-{unique_id}"
    owner_value = f"occ-owner-{unique_id}"
    collab_value = f"occ-collab-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, seed)
    await flows_chat_wait_saved(page)
    share = await flows_chat_create_share(page, permission="interact")
    code = share.share_url.rstrip("/").split("/l/")[-1]

    collaborator = await page.context.new_page()
    collaborator.set_default_timeout(45_000)
    try:
        await collaborator.goto(
            f"{frontend_ui.origin}/l/{code}",
            wait_until="domcontentloaded",
        )
        await collaborator.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
        await expect(collaborator.locator("platform-flow-ui").first).to_be_visible(
            timeout=60_000
        )
        assert (
            await flows_chat_draft_value(collaborator, chat_selector="platform-flow-ui")
            == seed
        )

        await flows_chat_fill_draft(page, owner_value)
        await flows_chat_wait_saved(page)

        await flows_chat_fill_draft(
            collaborator, collab_value, chat_selector="platform-flow-ui"
        )
        await expect(
            collaborator.locator("platform-flow-ui .statusbar .status")
        ).to_contain_text(re.compile(r"conflict|Conflict|Offline|Saving", re.I), timeout=60_000)

        await collaborator.reload(wait_until="domcontentloaded")
        await expect(collaborator.locator("platform-flow-ui").first).to_be_visible(
            timeout=60_000
        )
        restored = await flows_chat_draft_value(
            collaborator, chat_selector="platform-flow-ui"
        )
        assert restored == owner_value
    finally:
        await collaborator.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_offline_mutation_restores_from_recovery_journal(
    flows_dense_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_dense_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"offline-journal-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    session_url = await flows_chat_session_url(page)
    session_id = unquote(session_url.rstrip("/").split("/session/")[-1])
    context_id = (
        session_id[len(f"{flow_id}:") :]
        if session_id.startswith(f"{flow_id}:")
        else session_id
    )

    await page.context.set_offline(True)
    await flows_chat_fill_draft(page, draft)
    journal = await page.evaluate(
        """({ flowId, contextId }) => {
            const prefix = 'linnex.flow-ui.journal.v1';
            for (let index = 0; index < window.localStorage.length; index += 1) {
                const key = window.localStorage.key(index);
                if (!key || !key.startsWith(prefix)) continue;
                if (!key.includes(flowId) || !key.includes(contextId)) continue;
                return JSON.parse(window.localStorage.getItem(key) || '[]');
            }
            return null;
        }""",
        {"flowId": flow_id, "contextId": context_id},
    )
    assert isinstance(journal, list) and len(journal) >= 1
    assert any(
        isinstance(item, dict) and str(item.get("path", "")).startswith("/values")
        for item in journal
    )

    await page.context.set_offline(False)
    await flows_chat_wait_saved(page)
    assert await flows_chat_draft_value(page) == draft

    await page.reload(wait_until="domcontentloaded")
    await flows_chat_wait_ready(page)
    assert await flows_chat_draft_value(page) == draft


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_interface_multi_page_survives_publish_and_reopen(
    flows_dense_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_dense_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("iface_pages", unique_id)
    await flows_api_create_chat_test_flow(flows_ui.origin, auth_token_system, flow_id)
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        await flows_dismiss_pwa_install_banner(page)
        await flows_interface_add_page(page)
        await flows_publish_editor(page)
        await page.reload(wait_until="domcontentloaded")
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        pages_again = page.locator("flows-interface-pages-panel").first
        await expect(pages_again.locator("button.page")).to_have_count(2, timeout=30_000)
        await expect(
            pages_again.locator("button.page").filter(has_text=re.compile(r"Page 2"))
        ).to_be_visible(timeout=30_000)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_runtime_multi_page_nav_after_publish(
    flows_dense_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_dense_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("iface_nav", unique_id)
    await flows_api_create_chat_test_flow(flows_ui.origin, auth_token_system, flow_id)
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        await flows_dismiss_pwa_install_banner(page)
        await flows_interface_add_page(page)
        await flows_publish_editor(page)

        await flows_open_chat_page(page, flows_ui, flow_id)
        await flows_chat_wait_ready(page)
        await flows_dismiss_pwa_install_banner(page)
        surface = page.locator("chat-page platform-flow-ui").first
        await expect(surface).to_be_visible(timeout=60_000)
        nav = surface.locator('nav[aria-label="Pages"]').first
        await expect(nav).to_be_visible(timeout=30_000)
        await expect(nav.locator("button")).to_have_count(2, timeout=15_000)
        page_one = nav.locator("button").filter(has_text=re.compile(r"^Conversation$"))
        page_two = nav.locator("button").filter(has_text=re.compile(r"Page 2"))
        await expect(page_two).to_be_visible(timeout=15_000)
        # Publish leaves Page 2 active; switch away then back so navigate sync runs.
        await expect(page_one).to_be_visible(timeout=15_000)
        await page_one.click()
        await flows_chat_wait_saved(page)
        await page_two.click()
        await expect(page_two).to_have_attribute("aria-current", "page", timeout=15_000)
        await flows_chat_wait_saved(page)
        await expect(surface.locator(".statusbar")).to_contain_text("Saved", timeout=15_000)
        await expect(surface.locator(".statusbar")).not_to_contain_text(
            "Sync conflict", timeout=5_000
        )

        await page.reload(wait_until="domcontentloaded")
        await flows_chat_wait_ready(page)
        surface_again = page.locator("chat-page platform-flow-ui").first
        await expect(surface_again.locator(".statusbar")).to_contain_text("Saved", timeout=30_000)
        await expect(surface_again.locator(".statusbar")).not_to_contain_text(
            "Sync conflict", timeout=5_000
        )
        nav_again = surface_again.locator('nav[aria-label="Pages"]').first
        page_two_again = nav_again.locator("button").filter(has_text=re.compile(r"Page 2"))
        await expect(page_two_again).to_have_attribute("aria-current", "page", timeout=30_000)
        conversation_again = nav_again.locator("button").filter(
            has_text=re.compile(r"^Conversation$")
        )
        await expect(conversation_again).not_to_have_attribute("aria-current", "page")
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


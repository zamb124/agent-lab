"""Playwright E2E: reopen continuity + live share viewer (plan §25.4.1)."""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_chat_click_clear,
    flows_chat_create_share,
    flows_chat_draft_value,
    flows_chat_fill_draft,
    flows_chat_send_message,
    flows_chat_session_url,
    flows_chat_wait_ready,
    flows_chat_wait_saved,
    flows_expire_share_grant,
    flows_open_chat_page,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def flows_chat_browser_stack_ready(flows_service, frontend_service, taskiq_worker):
    _ = flows_service, frontend_service, taskiq_worker
    yield


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_draft_survives_reload_same_context(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"reopen-draft-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    session_url = await flows_chat_session_url(page)
    assert f"/flows/{flow_id}/session/" in session_url

    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("chat-page platform-flow-ui")).to_be_visible(timeout=60_000)
    await flows_chat_wait_ready(page)
    restored = await flows_chat_draft_value(page)
    assert restored == draft
    assert page.url.rstrip("/") == session_url.rstrip("/")


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_viewer_opens_same_context_read_only(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"share-draft-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    session_url = await flows_chat_session_url(page)
    session_id = unquote(session_url.rstrip("/").split("/session/")[-1])
    context_id = (
        session_id[len(f"{flow_id}:") :]
        if session_id.startswith(f"{flow_id}:")
        else session_id
    )

    share = await flows_chat_create_share(page, permission="viewer")
    code = share.share_url.rstrip("/").split("/l/")[-1]

    viewer = await page.context.new_page()
    viewer.set_default_timeout(45_000)
    try:
        await viewer.goto(
            f"{frontend_ui.origin}/l/{code}",
            wait_until="domcontentloaded",
        )
        await viewer.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
        parsed = urlsplit(viewer.url)
        assert parsed.path == "/flow-session-share"
        grant = parse_qs(parsed.query).get("grant", [""])[0]
        assert grant == share.grant_id

        surface = viewer.locator("platform-flow-ui").first
        await expect(surface).to_be_visible(timeout=60_000)
        await expect(surface.locator(".readonly-pill")).to_contain_text(
            "Read only",
            timeout=30_000,
        )
        await expect(surface.locator(".statusbar .status")).to_contain_text(
            "Live read-only view",
            timeout=30_000,
        )
        restored = await flows_chat_draft_value(viewer, chat_selector="platform-flow-ui")
        assert restored == draft
        context_prop = await surface.evaluate("(el) => el.contextId")
        assert context_prop == context_id
        flow_prop = await surface.evaluate("(el) => el.flowId")
        assert flow_prop == flow_id
        await expect(surface.locator("details.share")).to_have_count(0)
    finally:
        await viewer.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_second_tab_same_context_keeps_authoritative_draft(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"tab-draft-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    session_url = await flows_chat_session_url(page)

    second = await page.context.new_page()
    second.set_default_timeout(45_000)
    try:
        await second.goto(session_url, wait_until="domcontentloaded")
        await expect(second.locator("chat-page platform-flow-ui")).to_be_visible(
            timeout=60_000
        )
        await flows_chat_wait_ready(second)
        restored = await flows_chat_draft_value(second)
        assert restored == draft
        assert second.url.rstrip("/") == session_url.rstrip("/")
    finally:
        await second.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_new_screen_creates_separate_context(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"copy-draft-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    first_url = await flows_chat_session_url(page)

    await flows_chat_click_clear(page)
    await page.wait_for_function(
        "(previous) => window.location.href !== previous",
        arg=first_url,
        timeout=60_000,
    )
    second_url = await flows_chat_session_url(page)
    assert unquote(second_url) != unquote(first_url)
    restored = await flows_chat_draft_value(page)
    assert restored == ""


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_interact_can_edit_same_context(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"share-interact-{unique_id}"
    collaborator_draft = f"collab-edit-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    session_url = await flows_chat_session_url(page)
    session_id = unquote(session_url.rstrip("/").split("/session/")[-1])
    context_id = (
        session_id[len(f"{flow_id}:") :]
        if session_id.startswith(f"{flow_id}:")
        else session_id
    )

    share = await flows_chat_create_share(page, permission="editor")
    code = share.share_url.rstrip("/").split("/l/")[-1]

    collaborator = await page.context.new_page()
    collaborator.set_default_timeout(45_000)
    try:
        await collaborator.goto(
            f"{frontend_ui.origin}/l/{code}",
            wait_until="domcontentloaded",
        )
        await collaborator.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
        surface = collaborator.locator("platform-flow-ui").first
        await expect(surface).to_be_visible(timeout=60_000)
        await expect(surface.locator(".readonly-pill")).to_have_count(0)
        restored = await flows_chat_draft_value(
            collaborator, chat_selector="platform-flow-ui"
        )
        assert restored == draft
        context_prop = await surface.evaluate("(el) => el.contextId")
        assert context_prop == context_id

        await flows_chat_fill_draft(
            collaborator, collaborator_draft, chat_selector="platform-flow-ui"
        )
        await flows_chat_wait_saved(collaborator, chat_selector="platform-flow-ui")
        assert (
            await flows_chat_draft_value(collaborator, chat_selector="platform-flow-ui")
            == collaborator_draft
        )
    finally:
        await collaborator.close()

    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("chat-page platform-flow-ui")).to_be_visible(timeout=60_000)
    await flows_chat_wait_ready(page)
    owner_restored = await flows_chat_draft_value(page)
    assert owner_restored == collaborator_draft


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_submit_reply_survives_reload(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"reload-reply-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    session_url = await flows_chat_session_url(page)

    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("chat-page platform-flow-ui")).to_be_visible(timeout=60_000)
    await flows_chat_wait_ready(page)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)
    assert page.url.rstrip("/") == session_url.rstrip("/")


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_revoke_blocks_viewer_bootstrap(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"revoke-draft-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    share = await flows_chat_create_share(page, permission="viewer")
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
        restored = await flows_chat_draft_value(viewer, chat_selector="platform-flow-ui")
        assert restored == draft

        revoke_response = await page.request.delete(
            f"{flows_ui.origin}/flows/api/v1/flow-ui/shares/{share.grant_id}"
        )
        assert revoke_response.status == 204, await revoke_response.text()

        await viewer.reload(wait_until="domcontentloaded")
        await expect(viewer.get_by_text("Ссылка недоступна")).to_be_visible(timeout=60_000)
        await expect(
            viewer.get_by_text(re.compile(r"истекла или была отозвана", re.I))
        ).to_be_visible(timeout=30_000)
    finally:
        await viewer.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_revoke_from_owner_ui_blocks_viewer(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"revoke-ui-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    share = await flows_chat_create_share(page, permission="viewer")
    code = share.share_url.rstrip("/").split("/l/")[-1]

    viewer = await page.context.new_page()
    viewer.set_default_timeout(45_000)
    try:
        await viewer.goto(
            f"{frontend_ui.origin}/l/{code}",
            wait_until="domcontentloaded",
        )
        await viewer.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
        await expect(viewer.locator("platform-flow-ui").first).to_be_visible(timeout=60_000)

        share_menu = page.locator("chat-page platform-flow-ui details.share").first
        await expect(share_menu).to_be_visible(timeout=30_000)
        await share_menu.evaluate("(el) => { el.open = true; }")
        revoke_btn = share_menu.locator("button").filter(has_text=re.compile(r"^Revoke link$"))
        await expect(revoke_btn).to_be_attached(timeout=15_000)
        async with page.expect_response(
            lambda response: response.request.method == "DELETE"
            and f"/flows/api/v1/flow-ui/shares/{share.grant_id}" in response.url,
            timeout=30_000,
        ) as revoke_info:
            await revoke_btn.evaluate("(el) => el.click()")
        assert (await revoke_info.value).status == 204
        await expect(share_menu.locator('.share-result input[aria-label="Share link"]')).to_have_count(
            0, timeout=15_000
        )

        await viewer.reload(wait_until="domcontentloaded")
        await expect(viewer.get_by_text("Ссылка недоступна")).to_be_visible(timeout=60_000)
    finally:
        await viewer.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_expiry_blocks_viewer_bootstrap(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"expire-draft-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, draft)
    await flows_chat_wait_saved(page)
    share = await flows_chat_create_share(page, permission="viewer")
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
        assert await flows_chat_draft_value(viewer, chat_selector="platform-flow-ui") == draft

        await flows_expire_share_grant(share.grant_id)

        await viewer.reload(wait_until="domcontentloaded")
        await expect(viewer.get_by_text("Ссылка недоступна")).to_be_visible(timeout=60_000)
        await expect(
            viewer.get_by_text(re.compile(r"истекла или была отозвана", re.I))
        ).to_be_visible(timeout=30_000)
    finally:
        await viewer.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_redacts_message_value_for_viewer(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    secret = f"share-redact-secret-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_fill_draft(page, secret)
    await flows_chat_wait_saved(page)
    assert await flows_chat_draft_value(page) == secret

    share = await flows_chat_create_share(
        page,
        permission="viewer",
        redacted_value_paths=["/values/message"],
    )
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
        await expect(surface.locator(".readonly-pill")).to_contain_text(
            "Read only",
            timeout=30_000,
        )
        restored = await flows_chat_draft_value(viewer, chat_selector="platform-flow-ui")
        assert restored != secret
        assert secret not in (await viewer.content())
        assert await flows_chat_draft_value(page) == secret
    finally:
        await viewer.close()

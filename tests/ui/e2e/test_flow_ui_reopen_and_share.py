"""Playwright E2E: контекст переживает reload, share-ссылки открывают тот же A2A context."""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    FLOW_UI_COMPOSER_SELECTOR,
    FLOW_UI_READ_ONLY_PATTERN,
    FLOW_UI_READ_ONLY_STATUS_PATTERN,
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_chat_click_clear,
    flows_chat_composer_value,
    flows_chat_create_share,
    flows_chat_echo_payload,
    flows_chat_send_message,
    flows_chat_session_url,
    flows_chat_state_value,
    flows_chat_wait_ready,
    flows_doc_flow_id,
    flows_expire_share_grant,
    flows_open_chat_page,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def flows_chat_browser_stack_ready(flows_service, frontend_service, taskiq_worker):
    _ = flows_service, frontend_service, taskiq_worker
    yield


def _context_id(session_url: str, flow_id: str) -> str:
    session_id = unquote(session_url.rstrip("/").split("/session/")[-1])
    prefix = f"{flow_id}:"
    return session_id[len(prefix) :] if session_id.startswith(prefix) else session_id


async def _open_share(page: Page, frontend_ui: AppUI, share_url: str) -> Page:
    code = share_url.rstrip("/").split("/l/")[-1]
    viewer = await page.context.new_page()
    viewer.set_default_timeout(45_000)
    await viewer.goto(f"{frontend_ui.origin}/l/{code}", wait_until="domcontentloaded")
    await viewer.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
    await flows_chat_wait_ready(viewer, chat_selector="platform-flow-ui")
    return viewer


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_reply_survives_reload_same_context(
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
    assert f"/flows/{flow_id}/session/" in session_url

    await page.reload(wait_until="domcontentloaded")
    await flows_chat_wait_ready(page)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)
    assert page.url.rstrip("/") == session_url.rstrip("/")
    assert await flows_chat_composer_value(page) == ""


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_second_tab_same_context_shows_same_conversation(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"tab-reply-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    session_url = await flows_chat_session_url(page)

    second = await page.context.new_page()
    second.set_default_timeout(45_000)
    try:
        await second.goto(session_url, wait_until="domcontentloaded")
        await flows_chat_wait_ready(second)
        await expect(second.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)
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
    user_line = f"copy-reply-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    first_url = await flows_chat_session_url(page)

    await flows_chat_click_clear(page)
    await page.wait_for_function(
        "(previous) => window.location.href !== previous",
        arg=first_url,
        timeout=60_000,
    )
    second_url = await flows_chat_session_url(page)
    assert unquote(second_url) != unquote(first_url)
    await flows_chat_wait_ready(page)
    await expect(page.get_by_text(reply_text, exact=True)).to_have_count(0)
    assert await flows_chat_composer_value(page) == ""


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
    user_line = f"share-view-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    context_id = _context_id(await flows_chat_session_url(page), flow_id)

    share = await flows_chat_create_share(page, permission="viewer")
    viewer = await _open_share(page, frontend_ui, share.share_url)
    try:
        parsed = urlsplit(viewer.url)
        assert parsed.path == "/flow-session-share"
        assert parse_qs(parsed.query).get("grant", [""])[0] == share.grant_id

        surface = viewer.locator("platform-flow-ui").first
        await expect(surface.locator(".readonly-pill")).to_contain_text(
            FLOW_UI_READ_ONLY_PATTERN, timeout=30_000
        )
        await expect(surface.locator(".statusbar .status")).to_contain_text(
            FLOW_UI_READ_ONLY_STATUS_PATTERN, timeout=30_000
        )
        await expect(viewer.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)
        await expect(surface.locator(FLOW_UI_COMPOSER_SELECTOR)).to_have_count(0)
        await expect(surface.locator("details.share")).to_have_count(0)
        assert await surface.evaluate("(el) => el.contextId") == context_id
        assert await surface.evaluate("(el) => el.flowId") == flow_id
    finally:
        await viewer.close()


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_writer_continues_same_context(
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
    owner_line = f"share-owner-{unique_id}"
    collaborator_line = f"share-collab-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, owner_line)
    await expect(page.get_by_text(f"chat-ok:{owner_line}", exact=True)).to_be_visible(
        timeout=120_000
    )
    context_id = _context_id(await flows_chat_session_url(page), flow_id)

    share = await flows_chat_create_share(page, permission="editor")
    collaborator = await _open_share(page, frontend_ui, share.share_url)
    try:
        surface = collaborator.locator("platform-flow-ui").first
        await expect(surface.locator(".readonly-pill")).to_have_count(0)
        await expect(collaborator.get_by_text(f"chat-ok:{owner_line}", exact=True)).to_be_visible(
            timeout=60_000
        )
        assert await surface.evaluate("(el) => el.contextId") == context_id

        await flows_chat_send_message(collaborator, collaborator_line, chat_selector="platform-flow-ui")
        await expect(
            collaborator.get_by_text(f"chat-ok:{collaborator_line}", exact=True)
        ).to_be_visible(timeout=120_000)
    finally:
        await collaborator.close()

    # Ход соавтора — обычный Task того же context: владелец видит его после replay.
    await page.reload(wait_until="domcontentloaded")
    await flows_chat_wait_ready(page)
    await expect(page.get_by_text(f"chat-ok:{owner_line}", exact=True)).to_be_visible(timeout=60_000)
    await expect(page.get_by_text(f"chat-ok:{collaborator_line}", exact=True)).to_be_visible(
        timeout=60_000
    )


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
    user_line = f"revoke-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    share = await flows_chat_create_share(page, permission="viewer")

    viewer = await _open_share(page, frontend_ui, share.share_url)
    try:
        await expect(viewer.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)

        revoke_response = await page.request.delete(
            f"{flows_ui.origin}/flows/api/v1/flow-ui/shares/{share.grant_id}"
        )
        assert revoke_response.status == 200, await revoke_response.text()

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
    user_line = f"revoke-ui-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=True)).to_be_visible(
        timeout=120_000
    )
    share = await flows_chat_create_share(page, permission="viewer")

    viewer = await _open_share(page, frontend_ui, share.share_url)
    try:
        share_menu = page.locator("flows-chat-page platform-flow-ui details.share").first
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
        assert (await revoke_info.value).status == 200
        await expect(share_menu.locator('.share-result input[aria-label="Link"]')).to_have_count(
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
    user_line = f"expire-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    share = await flows_chat_create_share(page, permission="viewer")

    viewer = await _open_share(page, frontend_ui, share.share_url)
    try:
        await expect(viewer.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)

        await flows_expire_share_grant(share.grant_id)

        await viewer.reload(wait_until="domcontentloaded")
        await expect(viewer.get_by_text("Ссылка недоступна")).to_be_visible(timeout=60_000)
        await expect(
            viewer.get_by_text(re.compile(r"истекла или была отозвана", re.I))
        ).to_be_visible(timeout=30_000)
    finally:
        await viewer.close()


def _echo_payload_with_state_text(flow_id: str) -> dict[str, object]:
    """Echo flow whose interface reads ``response`` from state, so the ``state`` artifact carries it."""
    payload = flows_chat_echo_payload(flow_id)
    payload["interface"] = {
        "start_page_id": "main",
        "pages": [
            {
                "page_id": "main",
                "title": "Conversation",
                "blocks": [
                    {"type": "text", "block_id": "last-reply", "markdown": "Last reply: {?response}"},
                    {"type": "conversation", "block_id": "conversation"},
                ],
            }
        ],
    }
    return payload


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_redacts_state_path_for_viewer(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    frontend_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("share_redact", unique_id)
    user_line = f"redact-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    await flows_api_create_flow(flows_ui.origin, auth_token_system, _echo_payload_with_state_text(flow_id))
    viewer: Page | None = None
    try:
        await flows_open_chat_page(page, flows_ui, flow_id)
        await flows_chat_wait_ready(page)
        await flows_chat_send_message(page, user_line)
        await expect(
            page.locator('flows-chat-page platform-flow-ui [data-block-id="last-reply"]')
        ).to_contain_text(f"Last reply: {reply_text}", timeout=120_000)
        assert await flows_chat_state_value(page, "response") == reply_text

        share = await flows_chat_create_share(page, permission="viewer", redacted_paths=["/response"])
        viewer = await _open_share(page, frontend_ui, share.share_url)
        surface = viewer.locator("platform-flow-ui").first
        await expect(surface.locator(".readonly-pill")).to_contain_text(
            FLOW_UI_READ_ONLY_PATTERN, timeout=30_000
        )
        await expect(surface.locator('[data-block-id="last-reply"]')).to_be_visible(timeout=30_000)
        await expect(surface.locator('[data-block-id="last-reply"]')).not_to_contain_text(reply_text)
        assert await flows_chat_state_value(viewer, "response", chat_selector="platform-flow-ui") is None
        assert await flows_chat_state_value(page, "response") == reply_text
    finally:
        if viewer is not None:
            await viewer.close()
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

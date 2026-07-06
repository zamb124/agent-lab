"""Playwright E2E: flows SPA chat-page через единый `<platform-chat>`."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_chat_click_clear,
    flows_chat_send_message,
    flows_open_chat_page,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def flows_chat_browser_stack_ready(flows_service, taskiq_worker):
    """HTTP flows + TaskIQ worker перед browser-сценарием chat-page."""
    _ = flows_service, taskiq_worker
    yield


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_chat_page_send_and_stream_reply(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"spa-chat-{unique_id}"
    flow_id = flows_chat_test_agent

    sse_pattern = re.compile(rf"/flows/api/v1/{re.escape(flow_id)}(?:/|$)")
    async with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and sse_pattern.search(response.url) is not None
            and response.headers.get("content-type", "").startswith("text/event-stream")
        ),
        timeout=120_000,
    ):
        await flows_open_chat_page(page, flows_ui, flow_id)
        await flows_chat_send_message(page, user_line)

    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=True)).to_be_visible(timeout=120_000)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_chat_page_observability_opens_modals(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"spa-obs-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=True)).to_be_visible(timeout=120_000)

    bubble_actions = page.locator("platform-chat .bubble-observability-actions .tracing-btn")
    await expect(bubble_actions.first).to_be_visible(timeout=30_000)
    await bubble_actions.first.click()
    await expect(page.locator("flows-tracing-modal")).to_be_visible(timeout=30_000)

    await page.keyboard.press("Escape")
    await expect(page.locator("flows-tracing-modal")).to_be_hidden(timeout=15_000)

    logs_btn = page.locator("platform-chat .bubble-observability-actions .tracing-btn").nth(1)
    await expect(logs_btn).to_be_visible(timeout=15_000)
    await logs_btn.click()
    await expect(page.locator("flows-logs-modal")).to_be_visible(timeout=30_000)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_chat_page_cancel_active_task(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_slow_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"spa-cancel-{unique_id}"
    flow_id = flows_chat_slow_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_send_message(page, user_line)

    stop_btn = page.locator("platform-chat flows-chat-input button.stop-btn").first
    await expect(stop_btn).to_be_visible(timeout=30_000)
    await stop_btn.click()

    await expect(stop_btn).to_be_hidden(timeout=60_000)
    await expect(page.get_by_text("slow-done", exact=True)).to_be_hidden(timeout=5_000)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_chat_page_new_chat_clears_thread(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"spa-clear-{unique_id}"
    flow_id = flows_chat_test_agent
    reply_text = f"chat-ok:{user_line}"

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)

    await flows_chat_click_clear(page)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_hidden(timeout=30_000)

    user_bubbles = page.locator("platform-chat flows-chat-message[data-role='user']")
    await expect(user_bubbles).to_have_count(0, timeout=15_000)

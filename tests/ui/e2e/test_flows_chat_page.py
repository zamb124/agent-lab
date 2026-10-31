"""Playwright E2E: flows SPA flows-chat-page через `<platform-flow-ui>`."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    FLOW_UI_STOP_PATTERN,
    flows_chat_click_clear,
    flows_chat_composer_value,
    flows_chat_send_message,
    flows_chat_session_url,
    flows_chat_task_count,
    flows_chat_type_composer,
    flows_chat_wait_ready,
    flows_open_chat_page,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def flows_chat_browser_stack_ready(flows_service, taskiq_worker):
    """HTTP flows + TaskIQ worker перед browser-сценарием flows-chat-page."""
    _ = flows_service, taskiq_worker
    yield


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_chat_page_typing_does_not_invoke_flow(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    """Текст в composer живёт в браузере: без отправки нет Task и нет ответа graph."""
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    draft = f"spa-typing-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_type_composer(page, draft)
    _ = await flows_chat_session_url(page)
    assert await flows_chat_composer_value(page) == draft
    assert await flows_chat_task_count(page) == 0
    await expect(page.get_by_text(f"chat-ok:{draft}", exact=True)).to_have_count(0)


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
        await expect(
            page.locator("flows-chat-page platform-flow-ui .bubble.user").filter(has_text=user_line)
        ).to_be_visible(timeout=5_000)

    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=True)).to_be_visible(timeout=120_000)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_chat_page_task_feed_after_reply(
    flows_chat_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    flows_chat_test_agent: str,
    unique_id: str,
) -> None:
    """После ответа виден task/artifact feed (замена bubble observability)."""
    _ = flows_chat_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    user_line = f"spa-obs-{unique_id}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=True)).to_be_visible(timeout=120_000)
    await expect(
        page.locator("flows-chat-page platform-flow-ui .task-feed, flows-chat-page platform-flow-ui .task").first
    ).to_be_visible(timeout=30_000)


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

    stop_btn = page.locator("platform-flow-ui").get_by_role("button", name=FLOW_UI_STOP_PATTERN).first
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

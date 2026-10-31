"""Dense Flow UI continuity E2E without mocks: composer, share viewer, multi-page interface."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    FLOW_UI_COMPOSER_SELECTOR,
    FLOW_UI_READ_ONLY_PATTERN,
    INTERFACE_PAGE_TAB_SELECTOR,
    flows_api_create_chat_test_flow,
    flows_api_delete_flow,
    flows_chat_composer_value,
    flows_chat_create_share,
    flows_chat_send_message,
    flows_chat_task_count,
    flows_chat_type_composer,
    flows_chat_wait_ready,
    flows_dismiss_pwa_install_banner,
    flows_doc_flow_id,
    flows_interface_add_page,
    flows_interface_publish,
    flows_open_chat_page,
    flows_open_interface_editor_workspace,
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
async def test_flow_ui_composer_typing_does_not_invoke_flow(
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
    await flows_chat_type_composer(page, draft)
    assert await flows_chat_composer_value(page) == draft
    assert await flows_chat_task_count(page) == 0
    await expect(page.get_by_text(re.compile(rf"chat-ok:{re.escape(draft)}"))).to_have_count(0)

    # Текст composer'а живёт только в браузере: после reload контекст пуст, Task не создан.
    await page.reload(wait_until="domcontentloaded")
    await flows_chat_wait_ready(page)
    assert await flows_chat_composer_value(page) == ""
    assert await flows_chat_task_count(page) == 0
    await expect(page.get_by_text(re.compile(r"^chat-ok:"))).to_have_count(0)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_share_viewer_has_no_composer(
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
    user_line = f"view-block-{unique_id}"
    reply_text = f"chat-ok:{user_line}"
    flow_id = flows_chat_test_agent

    await flows_open_chat_page(page, flows_ui, flow_id)
    await flows_chat_wait_ready(page)
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(reply_text, exact=True)).to_be_visible(timeout=120_000)
    share = await flows_chat_create_share(page, permission="viewer")
    code = share.share_url.rstrip("/").split("/l/")[-1]

    viewer = await page.context.new_page()
    viewer.set_default_timeout(45_000)
    try:
        await viewer.goto(f"{frontend_ui.origin}/l/{code}", wait_until="domcontentloaded")
        await viewer.wait_for_url(re.compile(r"/flow-session-share\?"), timeout=60_000)
        await flows_chat_wait_ready(viewer, chat_selector="platform-flow-ui")
        surface = viewer.locator("platform-flow-ui").first
        await expect(viewer.get_by_text(reply_text, exact=True)).to_be_visible(timeout=60_000)
        await expect(surface.locator(".readonly-pill")).to_contain_text(
            FLOW_UI_READ_ONLY_PATTERN, timeout=30_000
        )
        await expect(surface.locator(FLOW_UI_COMPOSER_SELECTOR)).to_have_count(0)
        await expect(surface.get_by_role("button", name=re.compile(r"^(Send|Отправить)$"))).to_have_count(0)
        assert await flows_chat_task_count(viewer, chat_selector="platform-flow-ui") == 1
    finally:
        await viewer.close()


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
        await flows_interface_publish(page)
        await page.reload(wait_until="domcontentloaded")
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        tabs = page.locator(INTERFACE_PAGE_TAB_SELECTOR)
        await expect(tabs).to_have_count(2, timeout=30_000)
        await expect(tabs.filter(has_text=re.compile(r"New page|Новая страница"))).to_be_visible(
            timeout=30_000
        )
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
        await flows_interface_publish(page)

        await flows_open_chat_page(page, flows_ui, flow_id)
        await flows_chat_wait_ready(page)
        await flows_dismiss_pwa_install_banner(page)
        surface = page.locator("flows-chat-page platform-flow-ui").first
        nav = surface.locator('nav[aria-label="Pages"]').first
        await expect(nav).to_be_visible(timeout=30_000)
        await expect(nav.locator("button.page")).to_have_count(2, timeout=15_000)
        page_one = nav.locator("button.page").filter(has_text=re.compile(r"^Conversation$"))
        page_two = nav.locator("button.page").filter(has_text=re.compile(r"New page|Новая страница"))
        await expect(page_one).to_have_attribute("aria-current", "page", timeout=15_000)
        await page_two.click()
        await expect(page_two).to_have_attribute("aria-current", "page", timeout=15_000)
        await expect(page_one).not_to_have_attribute("aria-current", "page")
        await expect(surface.locator(FLOW_UI_COMPOSER_SELECTOR)).to_have_count(0)
        await expect(surface.locator(".statusbar .status")).to_contain_text("Live", timeout=15_000)

        # Навигация клиента не является ходом: после reload открывается стартовая страница.
        await page.reload(wait_until="domcontentloaded")
        await flows_chat_wait_ready(page)
        surface_again = page.locator("flows-chat-page platform-flow-ui").first
        nav_again = surface_again.locator('nav[aria-label="Pages"]').first
        await expect(
            nav_again.locator("button.page").filter(has_text=re.compile(r"^Conversation$"))
        ).to_have_attribute("aria-current", "page", timeout=30_000)
        await expect(surface_again.locator(FLOW_UI_COMPOSER_SELECTOR)).to_be_visible(timeout=15_000)
        assert await flows_chat_task_count(page) == 0
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

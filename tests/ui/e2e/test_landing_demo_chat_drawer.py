"""Playwright E2E: публичный landing demo drawer (platform-flow-ui embed_public)."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.fixture
def landing_chat_browser_stack_ready(
    frontend_service,
    flows_service,
    taskiq_worker,
):
    _ = frontend_service, flows_service, taskiq_worker
    yield


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_landing_demo_drawer_opens_platform_chat(
    landing_chat_browser_stack_ready,
    frontend_ui: AppUI,
    ui_page_anonymous: Page,
) -> None:
    _ = landing_chat_browser_stack_ready
    page = ui_page_anonymous
    page.set_default_timeout(45_000)

    await page.goto(f"{frontend_ui.origin}/", wait_until="domcontentloaded")
    await expect(page.locator("frontend-app")).to_be_visible(timeout=30_000)

    demo_section = page.locator("landing-home-demo-agents").first
    await expect(demo_section).to_be_visible(timeout=60_000)

    open_btn = demo_section.locator("glass-button, platform-button, button").filter(
        has_text=re.compile(r"Try|Попробовать|Open|Открыть|Chat|Чат", re.I)
    ).first
    await expect(open_btn).to_be_visible(timeout=30_000)
    await open_btn.click()

    drawer_chat = page.locator("landing-home-demo-agents platform-flow-ui").first
    await expect(drawer_chat).to_be_attached(timeout=30_000)

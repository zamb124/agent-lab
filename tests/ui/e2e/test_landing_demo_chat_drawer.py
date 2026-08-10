"""Playwright E2E: публичный landing demo drawer (flow-ui-drawer → platform-flow-ui embed_public)."""

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

    drawer_chat = page.locator(
        "landing-home-demo-agents flow-ui-drawer platform-flow-ui"
    ).first
    await expect(drawer_chat).to_be_attached(timeout=30_000)
    drawer = page.locator("landing-home-demo-agents flow-ui-drawer").first
    await expect(drawer).to_have_attribute("open", "", timeout=10_000)

    expand = drawer_chat.locator(
        "button[aria-label*='Expand'], button[title*='Expand'], "
        "button[aria-label*='Развернуть'], button[title*='Развернуть'], "
        "button[aria-label*='На весь'], button[title*='На весь'], "
        "button[aria-label*='Collapse'], button[title*='Свернуть']"
    ).first
    await expect(expand).to_be_visible(timeout=15_000)
    await expand.click()
    await expect(drawer).to_have_attribute("expanded", "", timeout=5_000)

    # Catalog VoiceInput control in composer (dictation fallback or session toggle).
    mic = drawer_chat.locator(
        "platform-voice-dictation, button.composer-voice-session, "
        "button[aria-label*='voice' i], button[aria-label*='эфир' i], "
        "button[aria-label*='диктов' i], button[aria-label*='голос' i], "
        "button[title*='голос' i], button[title*='voice' i]"
    ).first
    await expect(mic).to_be_attached(timeout=15_000)

"""Desktop E2E helpers: Playwright pairing."""

from __future__ import annotations

import re

from playwright.async_api import Page, expect


async def fetch_pairing_code_from_settings(page: Page, settings_url: str) -> str:
    await page.goto(settings_url, wait_until="domcontentloaded")
    await expect(page.locator("frontend-settings-page")).to_be_visible(timeout=30_000)
    agent_tab = page.locator("frontend-settings-page .tab").filter(
        has_text=re.compile(r"HumanitecAgent")
    )
    await expect(agent_tab).to_be_visible(timeout=30_000)
    await agent_tab.click()
    connect_button = page.get_by_role(
        "button",
        name=re.compile(r"Подключить компьютер|Connect computer"),
    )
    await expect(connect_button).to_be_visible(timeout=30_000)
    await connect_button.click()
    pairing_locator = page.locator("frontend-settings-page .info-grid dd").filter(
        has_text=re.compile(r"\d{6}")
    )
    await expect(pairing_locator).to_be_visible(timeout=30_000)
    pairing_text = await pairing_locator.inner_text()
    digits = re.sub(r"\D", "", pairing_text)
    if len(digits) != 6:
        raise AssertionError(f"pairing code must be 6 digits, got {pairing_text!r}")
    return digits

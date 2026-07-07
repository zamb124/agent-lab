"""Playwright shadow DOM helpers for Lit platform components."""

from __future__ import annotations

from playwright.async_api import Locator, Page


async def shadow_locator(page: Page, host_selector: str, inner_selector: str) -> Locator:
    """Return a Playwright locator targeting an element inside a shadow root."""

    handle = await page.evaluate_handle(
        """
        ([hostSelector, innerSelector]) => {
            const host = document.querySelector(hostSelector);
            if (!host || !host.shadowRoot) {
                throw new Error(`shadow host missing: ${hostSelector}`);
            }
            const node = host.shadowRoot.querySelector(innerSelector);
            if (!node) {
                throw new Error(`shadow node missing: ${innerSelector}`);
            }
            return node;
        }
        """,
        [host_selector, inner_selector],
    )
    return handle.as_element()  # type: ignore[return-value]

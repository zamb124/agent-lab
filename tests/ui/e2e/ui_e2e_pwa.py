"""Общий dismiss pwa-install-banner для UI E2E (баннер в shadow DOM PlatformApp)."""

from __future__ import annotations

import re

from playwright.async_api import Page

# Обходит light + shadow: document.querySelectorAll не видит host внутри shadow.
_DISMISS_PWA_JS = """
() => {
    localStorage.setItem('pwa-banner-dismissed', 'true');
    const dismissOne = (banner) => {
        banner._dismissed = true;
        banner.removeAttribute('visible');
        banner.style.setProperty('display', 'none', 'important');
        banner.style.setProperty('pointer-events', 'none', 'important');
        if (typeof banner.requestUpdate === 'function') {
            banner.requestUpdate();
        }
    };
    const walk = (root) => {
        if (!root || typeof root.querySelectorAll !== 'function') return;
        for (const banner of root.querySelectorAll('pwa-install-banner')) {
            dismissOne(banner);
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) walk(el.shadowRoot);
        }
    };
    walk(document);
}
"""


async def ui_e2e_dismiss_pwa_install_banner(page: Page) -> None:
    """Убирает PWA-баннер во всех shadow-деревьях — иначе z-index 9999 перехватывает клики."""
    await page.evaluate(_DISMISS_PWA_JS)
    later = page.get_by_role("button", name=re.compile(r"Later|Позже", re.I))
    if await later.count() > 0 and await later.first.is_visible():
        await later.first.evaluate("(el) => el.click()")
        await page.evaluate(_DISMISS_PWA_JS)

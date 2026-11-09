"""Diagnostic probe — NOT a permanent test. Hit-test the call-overlay chat toggle."""

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_probe_overlay_toggle_hit(
    sync_ui,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await sync_e2e_open_with_namespace(sync_ui, page, unique_id, suffix="probe")
    await sync_e2e_create_topic_channel_and_open(
        page, unique_id, channel_prefix="Проба звонка"
    )

    call_button = page.locator("sync-chat-header button.icon-btn.accent").first
    await expect(call_button).to_be_visible(timeout=30_000)
    await call_button.click()

    await expect(page.locator("sync-app")).to_have_attribute(
        "data-call-active", "", timeout=90_000
    )
    overlay = page.locator("sync-call-overlay-modal")
    await expect(overlay).to_be_visible(timeout=30_000)

    modals = await page.evaluate(
        """() => {
            const out = [];
            const walk = (root) => {
                for (const el of root.querySelectorAll('sync-call-overlay-modal')) {
                    const cs = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    out.push({
                        open: el.hasAttribute('open'),
                        closing: el.hasAttribute('closing'),
                        pe: cs.pointerEvents,
                        disp: cs.display,
                        vis: cs.visibility,
                        z: cs.zIndex,
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        parent: el.parentElement ? el.parentElement.tagName : null,
                    });
                }
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) walk(el.shadowRoot);
                }
            };
            walk(document);
            return out;
        }"""
    )
    print(f"\n=== MODALS: {modals}")

    toggle = overlay.locator(
        'button.ctrl[title="Показать чат"], button.ctrl[title="Show chat"]'
    ).first
    await expect(toggle).to_be_visible(timeout=120_000)
    await page.wait_for_timeout(2000)

    handle = await toggle.element_handle()
    info = await handle.evaluate(
        """(btn) => {
            const r = btn.getBoundingClientRect();
            const cx = r.x + r.width / 2;
            const cy = r.y + r.height / 2;
            const stack = document.elementsFromPoint(cx, cy).map((el) => {
                const cs = getComputedStyle(el);
                const er = el.getBoundingClientRect();
                return {
                    tag: el.tagName,
                    cls: (el.className || '').toString().slice(0, 60),
                    pe: cs.pointerEvents,
                    vis: cs.visibility,
                    z: cs.zIndex,
                    rect: {x: Math.round(er.x), y: Math.round(er.y), w: Math.round(er.width), h: Math.round(er.height)},
                };
            });
            const chain = [];
            let n = btn;
            while (n) {
                const cs = getComputedStyle(n);
                const er = n.getBoundingClientRect();
                chain.push({
                    tag: n.tagName,
                    cls: (n.className || '').toString().slice(0, 60),
                    pe: cs.pointerEvents,
                    vis: cs.visibility,
                    pos: cs.position,
                    rect: {x: Math.round(er.x), y: Math.round(er.y), w: Math.round(er.width), h: Math.round(er.height)},
                });
                n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
            }
            return {box: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}, center: {x: cx, y: cy}, stack, chain};
        }"""
    )
    print(f"\n=== INFO: {info}")

    try:
        await toggle.click(timeout=10_000)
        print("=== CLICK: ok")
    except Exception as e:
        print(f"=== CLICK FAILED: {str(e)[:800]}")

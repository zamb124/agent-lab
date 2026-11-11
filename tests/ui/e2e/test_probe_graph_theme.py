"""Probe v2: таймлайн data-theme и состояние graph-canvas."""
import pytest
from playwright.async_api import Page, ViewportSize, expect
from tests.ui.e2e.crm_activity_tasks_helpers import (
    crm_api_create_entity, crm_api_ensure_namespace,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_activate_namespace_for_next_load
from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_probe_graph_theme(
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = f"g_{unique_id}"
    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)
    await crm_api_create_entity(
        crm_ui.origin, auth_token_system, entity_type="note",
        name=f"Заметка {unique_id}", namespace=namespace,
    )
    await crm_ui.open(page)
    await page.set_viewport_size(ViewportSize(width=1440, height=900))
    await sync_e2e_activate_namespace_for_next_load(page, namespace)

    await page.evaluate(
        """() => {
            window.__themeLog = [];
            const obs = new MutationObserver((muts) => {
                for (const m of muts) {
                    window.__themeLog.push({
                        t: performance.now()|0,
                        theme: document.documentElement.getAttribute('data-theme'),
                    });
                }
            });
            obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        }"""
    )
    await page.goto(f"{crm_ui.origin}/crm/graph", wait_until="domcontentloaded")
    await expect(page.locator("crm-graph-page")).to_be_visible(timeout=60_000)
    await page.wait_for_timeout(15000)
    info = await page.evaluate(
        """() => {
            const walk = (root, sel) => {
                let cur = root.querySelector ? null : null;
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) {
                        const hit = el.shadowRoot.querySelector(sel);
                        if (hit) return hit;
                        const deep = walk(el.shadowRoot, sel);
                        if (deep) return deep;
                    }
                }
                return null;
            };
            const gc = walk(document, 'graph-canvas');
            const div = gc?.shadowRoot?.querySelector('#graph-canvas');
            return {
                theme_log: window.__themeLog,
                final_theme: document.documentElement.getAttribute('data-theme'),
                gc_found: !!gc,
                last_applied: gc ? gc._lastAppliedTheme : null,
                theme_select_val: gc?._themeSelect?.value,
                div_exists: !!div,
                storage: Object.entries(localStorage).filter(([k]) => k.includes('theme')),
            };
        }"""
    )
    print("PROBE2:", info)

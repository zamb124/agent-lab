"""Хелперы Evaluation Lab для UI E2E сценариев Flows."""

from __future__ import annotations

import re

from playwright.async_api import Locator, Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_click_platform_button,
    flows_open_evaluation_from_editor,
)
from tests.ui.harness import AppUI


async def flows_open_evaluation_page(page: Page, flows_ui: AppUI, flow_id: str) -> Locator:
    await flows_open_evaluation_from_editor(page, flows_ui, flow_id)
    return page.locator("flows-evaluation-page").first


flows_eval_open_evaluation_page = flows_open_evaluation_page


async def flows_eval_create_suite(page: Page) -> None:
    page_el = page.locator("flows-evaluation-page").first
    create_btn = page_el.locator(
        'flows-evaluation-suite-sidebar platform-button[aria-label*="suite" i], '
        'flows-evaluation-suite-sidebar platform-button[aria-label*="набор" i]'
    ).first
    await expect(create_btn).to_be_visible(timeout=10_000)
    await create_btn.locator("button").first.click()
    suite_row = page_el.locator("flows-evaluation-suite-sidebar .suite-list .row").first
    await expect(suite_row).to_be_visible(timeout=10_000)


async def flows_eval_open_templates_menu(page: Page) -> None:
    toolbar = page.locator("flows-evaluation-run-toolbar").first
    await expect(toolbar).to_be_visible(timeout=10_000)
    await flows_click_platform_button(toolbar, "Templates", "Шаблоны")
    menu = toolbar.locator(".template-menu").first
    await expect(menu).to_be_visible(timeout=10_000)


async def flows_eval_add_case_from_template(page: Page, template_pattern: str) -> None:
    await flows_eval_open_templates_menu(page)
    toolbar = page.locator("flows-evaluation-run-toolbar").first
    template = toolbar.locator(".template-item").filter(has_text=re.compile(template_pattern)).first
    await expect(template).to_be_visible(timeout=10_000)
    await template.click()
    editor = page.locator("flows-evaluation-case-editor").first
    await expect(editor).to_be_visible(timeout=10_000)


async def flows_eval_select_panel(page: Page, panel_pattern: str) -> None:
    page_el = page.locator("flows-evaluation-page").first
    panel_btn = page_el.locator("flows-evaluation-suite-sidebar .panel-list .row").filter(
        has_text=re.compile(panel_pattern)
    ).first
    await expect(panel_btn).to_be_visible(timeout=30_000)
    await panel_btn.click()


async def flows_eval_run(page: Page) -> None:
    toolbar = page.locator("flows-evaluation-run-toolbar").first
    await expect(toolbar).to_be_visible(timeout=30_000)
    await flows_click_platform_button(toolbar, "Run", "Запустить")


async def flows_eval_wait_run_finished(page: Page) -> None:
    toolbar = page.locator("flows-evaluation-run-toolbar").first
    status = toolbar.locator(".status-pill").filter(
        has_text=re.compile(r"completed|failed|cancelled|заверш", re.I)
    ).first
    await expect(status).to_be_visible(timeout=180_000)


async def flows_eval_open_compare_panel(page: Page) -> Locator:
    await flows_eval_select_panel(page, r"Compare|Сравн")
    panel = page.locator("flows-evaluation-compare-panel").first
    await expect(panel).to_be_visible(timeout=60_000)
    return panel


async def flows_eval_compare_runs(page: Page) -> None:
    panel = await flows_eval_open_compare_panel(page)
    compare = panel.locator("platform-button").filter(
        has_text=re.compile(r"^\s*(?:Compare|Сравнить)\s*$")
    ).first
    inner = compare.locator("button").first
    chips = panel.locator(".run-chip")
    await expect(chips).to_have_count(2, timeout=5_000)
    for index in range(await chips.count()):
        await chips.nth(index).click()
        if await inner.is_enabled():
            break
    await expect(inner).to_be_enabled(timeout=3_000)
    await compare.evaluate("(el) => el.click()")


async def flows_eval_set_baseline(page: Page) -> None:
    panel = page.locator("flows-evaluation-compare-panel").first
    await expect(panel).to_be_visible(timeout=60_000)
    baseline_btn = panel.locator("platform-button").filter(
        has_text=re.compile(r"Baseline|Базов|Set baseline|Сделать базовым")
    ).first
    await expect(baseline_btn).to_be_visible(timeout=30_000)
    await baseline_btn.locator("button").first.click()

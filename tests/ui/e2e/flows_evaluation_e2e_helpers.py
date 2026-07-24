"""Хелперы Evaluation Lab для UI E2E сценариев Flows."""

from __future__ import annotations

import re

import httpx
from playwright.async_api import Locator, Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_click_platform_button,
    flows_open_evaluation_from_editor,
    flows_set_platform_field,
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


async def flows_eval_create_blank_case(page: Page) -> Locator:
    page_el = page.locator("flows-evaluation-page").first
    create_btn = page_el.locator(
        'flows-evaluation-suite-sidebar platform-button[aria-label*="case" i], '
        'flows-evaluation-suite-sidebar platform-button[aria-label*="кейс" i], '
        'flows-evaluation-suite-sidebar platform-button[aria-label*="New case" i], '
        'flows-evaluation-suite-sidebar platform-button[aria-label*="Новый" i]'
    ).first
    await expect(create_btn).to_be_visible(timeout=10_000)
    await create_btn.locator("button").first.click()
    editor = page.locator("flows-evaluation-case-editor").first
    await expect(editor).to_be_visible(timeout=10_000)
    return editor


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
        has_text=re.compile(
            r"passed|failed|error|canceled|cancelled|completed|заверш",
            re.I,
        )
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


async def flows_eval_set_segmented(control: Locator, value: str) -> None:
    await expect(control).to_be_visible(timeout=10_000)
    await control.evaluate(
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        value,
    )


async def flows_eval_case_editor(page: Page) -> Locator:
    editor = page.locator("flows-evaluation-case-editor").first
    await expect(editor).to_be_visible(timeout=10_000)
    return editor


async def flows_eval_set_case_name(page: Page, name: str) -> None:
    editor = await flows_eval_case_editor(page)
    name_field = editor.locator("platform-field").filter(
        has_text=re.compile(r"Название|Name", re.I)
    ).first
    await flows_set_platform_field(name_field, name)


async def flows_eval_add_turn(page: Page) -> None:
    editor = await flows_eval_case_editor(page)
    await flows_click_platform_button(editor, "Добавить turn", "Add turn")
    turns = editor.locator(
        'platform-segmented-control[aria-label*="Turns" i], '
        'platform-segmented-control[aria-label*="turn" i]'
    ).first
    await expect(turns).to_be_visible(timeout=5_000)


async def flows_eval_set_input_kind(page: Page, kind: str) -> None:
    editor = await flows_eval_case_editor(page)
    control = editor.locator(
        'platform-segmented-control[aria-label*="Тип входа" i], '
        'platform-segmented-control[aria-label*="input" i]'
    ).first
    await flows_eval_set_segmented(control, kind)


async def flows_eval_set_check_type(page: Page, check_type: str) -> None:
    editor = await flows_eval_case_editor(page)
    control = editor.locator(
        'platform-segmented-control[aria-label*="Тип проверки" i], '
        'platform-segmented-control[aria-label*="check" i]'
    ).first
    await flows_eval_set_segmented(control, check_type)


async def flows_eval_set_text_input(page: Page, content: str) -> None:
    editor = await flows_eval_case_editor(page)
    field = editor.locator("platform-field").filter(
        has_text=re.compile(r"Входное сообщение|Input message|Input", re.I)
    ).first
    await flows_set_platform_field(field, content)


async def flows_eval_set_contains_values(page: Page, values: str) -> None:
    editor = await flows_eval_case_editor(page)
    field = editor.locator("platform-field").filter(
        has_text=re.compile(r"фрагмент|Contains|fragment", re.I)
    ).first
    await flows_set_platform_field(field, values)


async def flows_eval_save_case(page: Page) -> None:
    editor = await flows_eval_case_editor(page)
    await flows_click_platform_button(editor, "Создать", "Create", "Сохранить", "Save")


async def flows_eval_create_rubric(
    page: Page,
    *,
    name: str,
    prompt: str,
    threshold: str = "7",
) -> None:
    editor = await flows_eval_case_editor(page)
    await flows_click_platform_button(editor, "Новая рубрика", "New rubric")
    name_field = editor.locator("platform-field").filter(
        has_text=re.compile(r"Название рубрики|Rubric name", re.I)
    ).first
    threshold_field = editor.locator("platform-field").filter(
        has_text=re.compile(r"Pass threshold|threshold", re.I)
    ).first
    prompt_field = editor.locator("platform-field").filter(
        has_text=re.compile(r"Промпт критериев|Rubric prompt|criteria", re.I)
    ).first
    await flows_set_platform_field(name_field, name)
    await flows_set_platform_field(threshold_field, threshold)
    await flows_set_platform_field(prompt_field, prompt)
    await flows_click_platform_button(editor, "Создать рубрику", "Create rubric")


async def flows_eval_create_judge_node(page: Page) -> None:
    editor = await flows_eval_case_editor(page)
    await flows_click_platform_button(editor, "Создать judge node", "Create judge node")
    judge_field = editor.locator("platform-field").filter(
        has_text=re.compile(r"Judge llm_node|Judge", re.I)
    ).first
    await expect(judge_field).to_be_visible(timeout=15_000)
    embedded = page.locator("flows-embedded-tool-config-modal").first
    await expect(embedded).to_be_visible(timeout=15_000)
    closed = await page.evaluate(
        """
        () => {
            const el = document.querySelector('flows-embedded-tool-config-modal');
            if (!el) return false;
            if (typeof el.close === 'function') {
                el.close();
                return true;
            }
            el.open = false;
            el.removeAttribute('open');
            return true;
        }
        """
    )
    if closed is not True:
        raise AssertionError("flows-embedded-tool-config-modal did not close after judge create")
    await expect(embedded).to_be_hidden(timeout=15_000)


async def flows_eval_api_list_cases(
    origin: str,
    auth_token: str,
    suite_id: str,
) -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        timeout=60.0,
    ) as client:
        response = await client.get(f"/flows/api/v1/evaluation/suites/{suite_id}/cases")
    _ = response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("cases list must return object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("cases list must return items[]")
    result: list[dict[str, object]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(item)
    return result


async def flows_eval_api_get_case(
    origin: str,
    auth_token: str,
    suite_id: str,
    case_id: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        timeout=60.0,
    ) as client:
        response = await client.get(
            f"/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}"
        )
    _ = response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("case GET must return object")
    return payload


async def flows_eval_api_list_suites(
    origin: str,
    auth_token: str,
    flow_id: str,
) -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        timeout=60.0,
    ) as client:
        response = await client.get(
            "/flows/api/v1/evaluation/suites",
            params={"flow_id": flow_id},
        )
    _ = response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("suites list must return object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("suites list must return items[]")
    result: list[dict[str, object]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(item)
    return result

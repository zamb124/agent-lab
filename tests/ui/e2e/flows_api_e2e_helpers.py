"""Хелперы API Console для UI E2E сценариев Flows."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx2
from playwright.async_api import Locator, Page, expect

from tests.fixtures.variables_helpers import upsert_static_variable_via_secrets_http
from tests.ui.e2e.flows_e2e_helpers import (
    flows_click_editor_overflow,
    flows_click_platform_button,
    flows_dismiss_pwa_install_banner,
)
from tests.ui.harness import AppUI


def flows_api_console_docs_payload(flow_id: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": "API Console docs flow",
        "description": "Deterministic flow for API Console documentation.",
        "entry": "compose",
        "nodes": {
            "compose": {
                "type": "code",
                "name": "Compose API response",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = "
                    "f\"API_DOC_OK:{args['salutation']}|"
                    "{args['target_branch_id']}|{args['customer_name']}|{args['extra']}\"\n"
                    "    return state\n"
                ),
                "input_mapping": {
                    "salutation": "@var:salutation",
                    "target_branch_id": "@var:target_branch_id",
                    "customer_name": "@var:customer_name",
                    "extra": "@var:extra",
                },
                "pos_x": 520,
                "pos_y": 280,
            }
        },
        "edges": [{"from_node": "compose", "to_node": None}],
        "variables": {
            "salutation": {"value": "hello-from-flow", "public": True, "title": "Greeting", "order": 1},
            "customer_name": {"value": "Anna", "public": True, "title": "Customer name", "order": 2},
            "target_branch_id": {
                "value": "flow-default-target",
                "public": False,
                "title": "Target branch variable",
                "order": 3,
            },
            "extra": {"value": "flow-extra", "public": True, "title": "Extra payload", "order": 4},
            "api_secret": {
                "value": "@var:external_api_token",
                "secret": True,
                "public": False,
                "title": "External API token",
                "order": 5,
            },
        },
        "tags": ["docs", "scenario", "api"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


async def flows_seed_company_secret_var(
    auth_headers: dict[str, str],
    key: str,
    value: str,
    *,
    secret: bool = True,
) -> None:
    async with httpx2.AsyncClient(
        base_url="http://localhost:9022",
        headers=auth_headers,
        timeout=60.0,
    ) as client:
        await upsert_static_variable_via_secrets_http(
            client,
            key,
            value,
            secret=secret,
            shared_for_execution=True,
        )


async def flows_open_api_console_modal(page: Page, flows_ui: AppUI, flow_id: str) -> Locator:
    await page.set_viewport_size({"width": 1600, "height": 920})
    await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    await flows_click_editor_overflow(
        page,
        "API and A2A specification",
        "API и A2A",
        "API",
        "editor_header.menu_api",
        icon="api",
    )
    modal = page.locator("flows-api-console-modal[open], flows-api-console-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_api_console_click_nav(modal: Locator, label_pattern: str) -> None:
    button = modal.locator("platform-segmented-control.api-nav button.segment").filter(
        has_text=re.compile(label_pattern)
    ).first
    await expect(button).to_be_visible(timeout=30_000)
    await button.evaluate("(el) => el.click()")


async def flows_api_console_click_mode(modal: Locator, label_pattern: str) -> None:
    button = modal.locator(
        ".mode-tabs button.segment, platform-segmented-control.mode-tabs button.segment"
    ).filter(has_text=re.compile(label_pattern)).first
    await expect(button).to_be_visible(timeout=30_000)
    await button.evaluate("(el) => el.click()")


async def flows_api_console_set_run_variables(modal: Locator, variables: dict[str, Any]) -> None:
    value = json.dumps(variables, ensure_ascii=False, indent=2)
    editor = modal.locator("flows-code-editor.api-json-editor.compact").first
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        value,
    )


async def flows_api_console_run_and_wait(modal: Locator) -> None:
    page = modal.page
    await flows_dismiss_pwa_install_banner(page)
    await expect(modal).to_be_visible(timeout=15_000)
    await flows_click_platform_button(modal, "Run", "Запустить", timeout=30_000)
    result = modal.locator(".assistant-response").filter(
        has_text=re.compile(r"API_DOC_OK|Task submitted|completed|submitted")
    ).first
    if await result.count() == 0:
        result = modal.get_by_text(re.compile(r"API_DOC_OK|Task submitted|completed|submitted")).first
    try:
        await expect(result).to_be_visible(timeout=120_000)
    except AssertionError:
        # Модалка иногда теряет host после длительного poll — ищем ответ на странице.
        page_result = page.get_by_text(
            re.compile(r"API_DOC_OK|Task submitted|completed|submitted", re.I)
        ).first
        await expect(page_result).to_be_visible(timeout=30_000)


async def flows_api_console_open_inspector_tab(modal: Locator, tab_pattern: str) -> None:
    tab = modal.locator(".response-tabs button, .inspector-tabs button").filter(
        has_text=re.compile(tab_pattern)
    ).first
    await expect(tab).to_be_visible(timeout=30_000)
    await tab.click()

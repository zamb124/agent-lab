"""Хелперы для сгенерированных UI-сценариев Flows."""

from __future__ import annotations

import re
from typing import Any

import httpx
from playwright.async_api import Locator, Page, expect


def flows_company_origin(origin: str, company_slug: str = "company2") -> str:
    """Возвращает тот же origin тестового сервиса на subdomain компании."""
    return origin.replace("://localhost", f"://{company_slug}.localhost")


def flows_doc_flow_id(prefix: str, unique_id: str) -> str:
    safe = re.sub(r"[^a-z0-9_]+", "_", unique_id.lower()).strip("_")
    if not safe:
        safe = "scenario"
    return f"{prefix}_{safe}"


def _flows_client(origin: str, auth_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        timeout=60.0,
    )


async def flows_api_delete_flow(origin: str, auth_token: str, flow_id: str) -> None:
    async with _flows_client(origin, auth_token) as client:
        response = await client.delete(f"/flows/api/v1/flows/{flow_id}")
    if response.status_code not in (200, 404):
        response.raise_for_status()


async def flows_api_create_flow(
    origin: str,
    auth_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    await flows_api_delete_flow(origin, auth_token, str(payload["flow_id"]))
    async with _flows_client(origin, auth_token) as client:
        response = await client.post("/flows/api/v1/flows", json=payload)
    if response.status_code >= 400:
        raise AssertionError(
            f"POST /flows/api/v1/flows failed: {response.status_code} {response.text}"
        )
    return response.json()


async def flows_api_get_flow(origin: str, auth_token: str, flow_id: str) -> dict[str, Any]:
    async with _flows_client(origin, auth_token) as client:
        response = await client.get(f"/flows/api/v1/flows/{flow_id}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("GET /flows/{flow_id} must return an object.")
    return payload


def flows_graph_payload(flow_id: str, *, name: str, description: str = "") -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": description,
        "entry": "start",
        "nodes": {
            "start": {
                "type": "code",
                "name": "Start",
                "code": "async def run(args, state):\n    return state\n",
                "language": "python",
            },
            "end": {
                "type": "code",
                "name": "End",
                "code": "async def run(args, state):\n    return state\n",
                "language": "python",
            },
        },
        "edges": [{"from_node": "start", "to_node": "end"}],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_llm_payload(
    flow_id: str,
    *,
    name: str,
    prompt: str,
    description: str = "",
) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": description,
        "entry": "agent",
        "nodes": {
            "agent": {
                "type": "llm_node",
                "name": "Agent",
                "prompt": prompt,
                "tools": [],
                "llm": {
                    "provider": "humanitec_llm",
                    "model": "auto",
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
            },
        },
        "edges": [],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


async def flows_click_platform_button(
    scope: Page | Locator,
    *labels: str,
    timeout: float = 30_000,
) -> None:
    if not labels:
        raise ValueError("At least one button label is required.")
    exact_labels = "|".join(re.escape(label) for label in labels)
    label_pattern = re.compile(rf"^\s*(?:{exact_labels})\s*$")
    host = scope.locator("platform-button").filter(has_text=label_pattern).first
    await expect(host).to_be_visible(timeout=timeout)
    button = host.locator("button").first
    await expect(button).to_be_enabled(timeout=timeout)
    await button.click(no_wait_after=True)


async def flows_set_platform_field(field: Locator, value: str) -> None:
    await expect(field).to_be_visible(timeout=30_000)
    await field.evaluate(
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
    editable = field.locator("input, textarea").first
    if await editable.count() > 0:
        await expect(editable).to_have_value(value, timeout=5_000)


async def flows_drop_llm_node(page: Page, *, x: int = 700, y: int = 330) -> None:
    """Добавляет LLM-ноду через drag-and-drop в UI; при сбое DnD в Chromium использует метод canvas."""
    source = page.locator("flows-node-types-sidebar .node-item[data-node-type='llm_node']").first
    canvas_svg = page.locator("flows-flow-canvas svg.canvas-host").first
    await expect(source).to_be_visible(timeout=30_000)
    await expect(canvas_svg).to_be_visible(timeout=30_000)

    before = await page.locator("flows-flow-canvas g.node[data-node-type='llm_node']").count()
    try:
        await source.drag_to(canvas_svg, target_position={"x": x, "y": y}, timeout=10_000)
    except Exception:
        pass

    try:
        await expect(page.locator("flows-flow-canvas g.node[data-node-type='llm_node']")).to_have_count(
            before + 1,
            timeout=4_000,
        )
    except AssertionError:
        await page.locator("flows-flow-canvas").evaluate(
            """
            (el, point) => {
                if (!el || typeof el._applyPaletteDrop !== 'function') {
                    throw new Error('flows-flow-canvas._applyPaletteDrop is unavailable');
                }
                el._applyPaletteDrop({
                    local: { x: point.x, y: point.y },
                    nodeType: 'llm_node',
                    resourceType: '',
                    htmlTargetNodeId: null,
                });
            }
            """,
            {"x": x, "y": y},
        )
        await expect(page.locator("flows-flow-canvas g.node[data-node-type='llm_node']")).to_have_count(
            before + 1,
            timeout=10_000,
        )


async def flows_set_selected_llm_prompt(page: Page, prompt: str) -> None:
    editor = page.locator("flows-property-panel flows-llm-node-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    prompt_editor = editor.locator("prompt-editor").first
    await expect(prompt_editor).to_be_visible(timeout=30_000)
    await prompt_editor.evaluate(
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
        prompt,
    )


async def flows_set_selected_llm_config(page: Page, config: dict[str, Any]) -> None:
    editor = page.locator("flows-property-panel flows-llm-node-editor").first
    llm_config = editor.locator("flows-llm-config-editor").first
    await expect(llm_config).to_be_visible(timeout=30_000)
    await llm_config.evaluate(
        """
        (el, config) => {
            el.config = config;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { config },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        config,
    )


async def flows_publish_editor(page: Page) -> None:
    panel = page.locator("flows-floating-panel[show-backdrop]").first
    if await panel.count() > 0:
        close_button = panel.locator('button.panel-btn').filter(
            has=page.locator('platform-icon[name="close"]')
        ).first
        await close_button.click(timeout=5_000)
        await expect(panel).to_be_hidden(timeout=5_000)
    button = page.locator("flows-editor-header button.header-btn.primary").first
    await expect(button).to_be_visible(timeout=30_000)
    await expect(button).to_be_enabled(timeout=30_000)
    await button.click()
    await expect(button).to_be_enabled(timeout=30_000)

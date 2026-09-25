"""Хелперы для сгенерированных UI-сценариев Flows."""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

import httpx
from playwright.async_api import Locator, Page, expect
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.ui.e2e.ui_e2e_pwa import ui_e2e_dismiss_pwa_install_banner
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ELEMENT_IS_PAINTED_JS, LOADING_SELECTOR

if TYPE_CHECKING:
    from core.mail.models import MailboxBinding


def flows_company_origin(origin: str, company_slug: str | None = None) -> str:
    """Возвращает тот же origin тестового сервиса на subdomain компании (worker c2)."""
    from tests.ui.e2e_worker import ui_e2e_subdomain_company2

    slug = company_slug if company_slug is not None else ui_e2e_subdomain_company2()
    parsed = urlparse(origin)
    host = parsed.hostname
    if host is None or host.strip() == "":
        raise ValueError(f"Unsupported origin for flows company subdomain: {origin!r}")
    if host.endswith(".lvh.me"):
        new_host = f"{slug}.lvh.me"
    elif host == "localhost" or host.endswith(".localhost"):
        new_host = f"{slug}.localhost"
    else:
        raise ValueError(f"Unsupported origin for flows company subdomain: {origin!r}")
    netloc = new_host if parsed.port is None else f"{new_host}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


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
    if response.status_code not in (200, 403, 404):
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


async def flows_api_create_branch(
    origin: str,
    auth_token: str,
    flow_id: str,
    *,
    branch_id: str,
    name: str,
    description: str = "",
) -> dict[str, Any]:
    async with _flows_client(origin, auth_token) as client:
        response = await client.post(
            f"/flows/api/v1/{flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": name,
                "description": description,
            },
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST /flows/api/v1/{flow_id}/branches failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("POST branch must return an object.")
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
    tools: list[dict[str, Any]] | None = None,
    agent_skills: list[str] | None = None,
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
                "tools": tools if tools is not None else [],
                "agent_skills": agent_skills if agent_skills is not None else [],
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


def flows_llm_with_reflection_payload(
    flow_id: str,
    *,
    name: str,
    prompt: str,
    reflection_node_id: str = "reflection_1",
) -> dict[str, Any]:
    """Агент + reflection после него (для быстрых UI-сценариев без DnD)."""
    payload = flows_llm_payload(flow_id, name=name, prompt=prompt)
    nodes = payload["nodes"]
    if not isinstance(nodes, dict):
        raise TypeError("flows_llm_payload nodes must be a dict")
    nodes[reflection_node_id] = {
        "type": "reflection",
        "name": "Answer review",
        "pos_x": 420,
        "pos_y": 120,
        "llm": {
            "provider": "humanitec_llm",
            "model": "auto",
            "temperature": 0.0,
            "max_tokens": 512,
        },
        "critic_policy": {
            "policy_id": "final-answer-safety",
            "gate": "final_answer",
            "target": {"kind": "response"},
            "instruction": "Block vague or unsafe final answers.",
            "criteria": [
                {
                    "criterion_id": "clarity",
                    "description": "Answer must be concrete and actionable.",
                    "severity": "error",
                }
            ],
            "min_confidence": 0.8,
            "block_on_severities": ["error", "critical"],
            "exits": [
                {
                    "exit_id": "approved",
                    "label": "Approved",
                    "when": {"kind": "approved_true"},
                },
                {
                    "exit_id": "blocked",
                    "label": "Blocked",
                    "when": {"kind": "approved_false"},
                },
            ],
        },
    }
    agent = nodes["agent"]
    if isinstance(agent, dict):
        agent["pos_x"] = 80
        agent["pos_y"] = 120
    payload["edges"] = [
        {"from_node": "agent", "to_node": reflection_node_id},
        {
            "from_node": reflection_node_id,
            "to_node": None,
            "from_port": "approved",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "approved",
            },
        },
        {
            "from_node": reflection_node_id,
            "to_node": None,
            "from_port": "blocked",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "blocked",
            },
        },
    ]
    return payload


async def flows_click_platform_button(
    scope: Page | Locator,
    *labels: str,
    timeout: float = 30_000,
) -> None:
    if not labels:
        raise ValueError("At least one button label is required.")
    exact_labels = "|".join(re.escape(label) for label in labels)
    # Segmented tabs: "Catalog (1)", "Installed (2)".
    label_pattern = re.compile(rf"^\s*(?:{exact_labels})(?:\s*\(\d+\))?\s*$")
    host = scope.locator("platform-button").filter(has_text=label_pattern).first
    if await host.count() > 0:
        await expect(host).to_be_visible(timeout=timeout)
        button = host.locator("button").first
        await expect(button).to_be_enabled(timeout=timeout)
        await button.click(no_wait_after=True)
        return
    button = scope.get_by_role("button", name=label_pattern).first
    await expect(button).to_be_visible(timeout=timeout)
    await expect(button).to_be_enabled(timeout=timeout)
    await button.click(no_wait_after=True)


async def flows_set_platform_field(field: Locator, value: str) -> None:
    await expect(field).to_be_visible(timeout=5_000)
    # platform-field may retain hidden implementation inputs while switching
    # renderers/modes. Interact only with the actual user-facing control.
    editable = field.locator("input:visible, textarea:visible").first
    if await editable.count() > 0:
        await editable.fill(value)
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
        await expect(
            page.locator("flows-flow-canvas g.node[data-node-type='llm_node']")
        ).to_have_count(
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
        await expect(
            page.locator("flows-flow-canvas g.node[data-node-type='llm_node']")
        ).to_have_count(
            before + 1,
            timeout=10_000,
        )


async def flows_e2e_open_studio_prompt_section(page: Page) -> Locator:
    """Секция Prompt в Agent Focus."""
    studio = page.locator("flows-agent-focus-studio").first
    await expect(studio).to_be_visible(timeout=5_000)
    prompt_tab = (
        studio.locator("platform-segmented-control")
        .get_by_role(
            "button",
            name=re.compile(r"^Prompt$|^Промпт$", re.I),
        )
        .first
    )
    await expect(prompt_tab).to_be_visible(timeout=5_000)
    if await prompt_tab.get_attribute("aria-pressed") != "true":
        await prompt_tab.click()
    return studio


async def flows_set_selected_llm_prompt(
    page: Page,
    prompt: str,
    *,
    node_id: str | None = None,
) -> None:
    studio = page.locator("flows-agent-focus-studio").first
    if await studio.count() > 0 and await studio.is_visible():
        await flows_e2e_open_studio_prompt_section(page)
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor"
    ).first
    await expect(editor).to_be_visible(timeout=5_000)
    prompt_editor = editor.locator("platform-markdown-editor").first
    await expect(prompt_editor).to_be_visible(timeout=5_000)
    await prompt_editor.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.setValue === 'function') {
                el.setValue(value);
            }
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value, htmlValue: '', textValue: value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        prompt,
    )
    # Sticky patch через canvas ИЛИ agent-focus studio (_editor).
    # В layout=agent канвы нет в DOM — без studio patch промпт не попадает в branchData.
    host = page.locator("flows-flow-canvas, flows-agent-focus-studio").first
    await expect(host).to_be_visible(timeout=5_000)
    inject_js = """
        (el, ctx) => {
            const nextPrompt = ctx.prompt;
            const preferredId = ctx.nodeId;
            const editor = el && el._editor ? el._editor : null;
            if (!editor || typeof editor.updateBranchData !== 'function') {
                throw new Error('flows_set_selected_llm_prompt: editor unavailable');
            }
            let data = null;
            if (typeof el._branchData === 'function') {
                data = el._branchData();
            } else if (editor.state && typeof editor.state === 'object') {
                data = editor.state.branchData;
            }
            if (!data || typeof data !== 'object') {
                throw new Error('flows_set_selected_llm_prompt: branchData unavailable');
            }
            const nodes = data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            const selectedId = editor.state && typeof editor.state.selectedNodeId === 'string'
                ? editor.state.selectedNodeId
                : '';
            let nodeId = '';
            if (typeof preferredId === 'string' && preferredId !== '' && nodes[preferredId]) {
                nodeId = preferredId;
            } else if (selectedId !== '' && nodes[selectedId]) {
                nodeId = selectedId;
            } else if (Object.prototype.hasOwnProperty.call(nodes, 'agent')) {
                nodeId = 'agent';
            } else {
                const llmIds = Object.entries(nodes)
                    .filter(([, node]) => node && typeof node === 'object' && node.type === 'llm_node')
                    .map(([id]) => id);
                if (llmIds.length === 1) {
                    nodeId = llmIds[0];
                }
            }
            if (nodeId === '' || !nodes[nodeId]) {
                throw new Error(
                    'flows_set_selected_llm_prompt: selected llm node missing '
                    + JSON.stringify({ preferredId, selectedId, keys: Object.keys(nodes) })
                );
            }
            const prev = nodes[nodeId];
            const nextNode = { ...prev, prompt: nextPrompt };
            const next = { ...data, nodes: { ...nodes, [nodeId]: nextNode } };
            editor.updateBranchData({ data: next });
            editor.setDirty({ dirty: true });
            if (typeof editor.pushHistory === 'function') {
                editor.pushHistory({ snapshot: next });
            }
            return nodeId;
        }
    """
    verify_js = """
        (el, ctx) => {
            const editor = el && el._editor ? el._editor : null;
            let data = null;
            if (typeof el._branchData === 'function') {
                data = el._branchData();
            } else if (editor && editor.state) {
                data = editor.state.branchData;
            }
            const node = data && data.nodes ? data.nodes[ctx.nodeId] : null;
            return node && typeof node.prompt === 'string' ? node.prompt : null;
        }
    """
    inject_ctx = {"prompt": prompt, "nodeId": node_id if isinstance(node_id, str) else ""}
    for _attempt in range(3):
        patched_id = await host.evaluate(inject_js, inject_ctx)
        if not isinstance(patched_id, str) or patched_id == "":
            await asyncio.sleep(0.15)
            continue
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            current = await host.evaluate(verify_js, {"nodeId": patched_id})
            if isinstance(current, str) and current == prompt:
                return
            await asyncio.sleep(0.1)
    raise AssertionError(
        f"flows_set_selected_llm_prompt: prompt not sticky in branchData ({prompt!r})"
    )


async def flows_e2e_open_studio_model_section(page: Page) -> Locator:
    """Секция Model в Agent Focus — там flows-llm-config-editor."""
    studio = page.locator("flows-agent-focus-studio").first
    await expect(studio).to_be_visible(timeout=5_000)
    model_tab = (
        studio.locator("platform-segmented-control")
        .get_by_role(
            "button",
            name=re.compile(r"^Model$|^Модель$", re.I),
        )
        .first
    )
    await expect(model_tab).to_be_visible(timeout=5_000)
    if await model_tab.get_attribute("aria-pressed") != "true":
        await model_tab.click()
    return studio


async def flows_set_selected_llm_config(page: Page, config: dict[str, Any]) -> None:
    studio = page.locator("flows-agent-focus-studio").first
    if await studio.count() > 0 and await studio.is_visible():
        await flows_e2e_open_studio_model_section(page)
    editor = page.locator(
        "flows-floating-panel flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor"
    ).first
    await expect(editor).to_be_visible(timeout=5_000)
    llm_config = editor.locator("flows-llm-config-editor").first
    await expect(llm_config).to_be_visible(timeout=5_000)
    await llm_config.evaluate(
        """
        (el, nextConfig) => {
            el.config = nextConfig;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { config: nextConfig },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        config,
    )
    # Sticky patch в branchData: late load / studio sync могут откатить UI change.
    canvas = page.locator("flows-flow-canvas").first
    if await canvas.count() == 0:
        return
    inject_js = """
        (el, nextConfig) => {
            if (!el || !el._editor || typeof el._branchData !== 'function') {
                throw new Error('flows_set_selected_llm_config: canvas editor unavailable');
            }
            const data = el._branchData();
            const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            const selectedId = el._editor.selectedNodeId;
            const nodeId = typeof selectedId === 'string' && selectedId !== ''
                ? selectedId
                : (Object.prototype.hasOwnProperty.call(nodes, 'agent') ? 'agent' : '');
            if (nodeId === '' || !nodes[nodeId]) {
                throw new Error('flows_set_selected_llm_config: selected llm node missing');
            }
            const prev = nodes[nodeId];
            const nextNode = { ...prev, llm: { ...(prev.llm || {}), ...nextConfig } };
            const next = { ...data, nodes: { ...nodes, [nodeId]: nextNode } };
            el._editor.updateBranchData({ data: next });
            el._editor.setDirty({ dirty: true });
            el._editor.pushHistory({ snapshot: next });
            return nodeId;
        }
    """
    verify_js = """
        (el, ctx) => {
            if (!el || typeof el._branchData !== 'function') return null;
            const data = el._branchData();
            const node = data && data.nodes ? data.nodes[ctx.nodeId] : null;
            const llm = node && node.llm && typeof node.llm === 'object' ? node.llm : null;
            if (!llm) return null;
            return {
                temperature: llm.temperature,
                max_tokens: llm.max_tokens,
                model: llm.model,
                provider: llm.provider,
            };
        }
    """
    for _attempt in range(3):
        node_id = await canvas.evaluate(inject_js, config)
        if not isinstance(node_id, str) or node_id == "":
            await asyncio.sleep(0.15)
            continue
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            current = await canvas.evaluate(verify_js, {"nodeId": node_id})
            if (
                isinstance(current, dict)
                and current.get("temperature") == config.get("temperature")
                and current.get("max_tokens") == config.get("max_tokens")
            ):
                return
            await asyncio.sleep(0.1)
    raise AssertionError(
        f"flows_set_selected_llm_config: config not sticky in branchData ({config!r})"
    )


def flows_chat_echo_payload(
    flow_id: str,
    *,
    name: str = "Chat E2E Echo",
    response_prefix: str = "chat-ok",
) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "UI E2E echo agent for platform-flow-ui SPA",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "code",
                "name": "Echo",
                "code": (
                    "async def run(args, state):\n"
                    "    content = state.get('content', '')\n"
                    f"    state['response'] = f'{response_prefix}:' + content\n"
                    "    return state\n"
                ),
                "language": "python",
            },
        },
        "edges": [{"from_node": "main", "to_node": None}],
        "variables": {},
        "tags": ["e2e", "chat"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_chat_slow_payload(flow_id: str, *, sleep_seconds: float = 30.0) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": "Chat E2E Slow",
        "description": "UI E2E slow agent for cancel test",
        "entry": "slow",
        "nodes": {
            "slow": {
                "type": "code",
                "name": "Slow",
                "code": (
                    "import asyncio\n"
                    "async def run(args, state):\n"
                    f"    await asyncio.sleep({sleep_seconds})\n"
                    "    state['response'] = 'slow-done'\n"
                    "    return state\n"
                ),
                "language": "python",
            },
        },
        "edges": [{"from_node": "slow", "to_node": None}],
        "variables": {},
        "tags": ["e2e", "chat"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


async def flows_api_create_chat_test_flow(
    origin: str,
    auth_token: str,
    flow_id: str,
    *,
    slow: bool = False,
) -> dict[str, Any]:
    payload = flows_chat_slow_payload(flow_id) if slow else flows_chat_echo_payload(flow_id)
    return await flows_api_create_flow(origin, auth_token, payload)


async def flows_open_chat_page(
    page: Page,
    flows_ui: AppUI,
    flow_id: str,
    *,
    branch_id: str = "base",
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded",
) -> None:
    branch_segment = "" if branch_id in {"", "base", "default"} else f"/branch/{branch_id}"
    url = f"{flows_ui.origin}/flows/{flow_id}{branch_segment}"
    await page.goto(url, wait_until=wait_until)
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("chat-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("chat-page platform-flow-ui")).to_be_visible(timeout=30_000)


FLOW_UI_COMPOSER_SELECTOR = 'textarea[data-canon="composer"]'
FLOW_UI_SEND_PATTERN = re.compile(r"^(Send|Отправить)$")
FLOW_UI_STOP_PATTERN = re.compile(r"^(Stop|Остановить)$")
FLOW_UI_READ_ONLY_PATTERN = re.compile(r"Read only|Только просмотр")
FLOW_UI_READ_ONLY_STATUS_PATTERN = re.compile(r"Live read-only view|Просмотр без изменений")


def flows_chat_composer(page: Page, chat_selector: str = "chat-page platform-flow-ui") -> Locator:
    return page.locator(chat_selector).first.locator(FLOW_UI_COMPOSER_SELECTOR).first


async def flows_chat_send_message(
    page: Page,
    text: str,
    *,
    chat_selector: str = "chat-page platform-flow-ui",
) -> None:
    root = page.locator(chat_selector).first
    await expect(root).to_be_attached(timeout=30_000)
    textarea = root.locator(FLOW_UI_COMPOSER_SELECTOR).first
    await expect(textarea).to_be_visible(timeout=30_000)
    await textarea.fill(text)
    send = root.get_by_role("button", name=FLOW_UI_SEND_PATTERN).first
    await expect(send).to_be_enabled(timeout=10_000)
    await send.click()


async def flows_chat_click_clear(page: Page) -> None:
    clear_btn = (
        page.locator("chat-page platform-button")
        .filter(has_text=re.compile(r"New screen|Новый экран"))
        .first
    )
    await expect(clear_btn).to_be_visible(timeout=30_000)
    await clear_btn.locator("button").first.click()


async def flows_chat_wait_ready(
    page: Page,
    *,
    chat_selector: str = "chat-page platform-flow-ui",
) -> None:
    """Interface loaded, context opened (ListTasks replayed) and the page rendered."""
    root = page.locator(chat_selector).first
    await expect(root).to_be_visible(timeout=60_000)
    await expect(root.locator(".skeleton")).to_have_count(0, timeout=60_000)
    await expect(root.locator("flow-ui-page")).to_be_visible(timeout=60_000)
    handle = await root.element_handle()
    if handle is None:
        raise AssertionError(f"flows_chat_wait_ready: no element for {chat_selector!r}")
    await page.wait_for_function(
        """(el) => Boolean(el.store?.document)
            && typeof el.contextId === 'string' && el.contextId !== ''
            && el.client !== null""",
        arg=handle,
        timeout=60_000,
    )


async def flows_chat_type_composer(
    page: Page,
    text: str,
    *,
    chat_selector: str = "chat-page platform-flow-ui",
) -> None:
    """Type into the conversation composer without sending; the value stays in the browser."""
    textarea = flows_chat_composer(page, chat_selector)
    await expect(textarea).to_be_visible(timeout=30_000)
    await textarea.fill(text)


async def flows_chat_composer_value(
    page: Page,
    *,
    chat_selector: str = "chat-page platform-flow-ui",
) -> str:
    textarea = flows_chat_composer(page, chat_selector)
    await expect(textarea).to_be_visible(timeout=30_000)
    value = await textarea.input_value()
    if not isinstance(value, str):
        raise AssertionError(f"composer value must be str, got {type(value)}")
    return value


async def flows_chat_task_count(
    page: Page,
    *,
    chat_selector: str = "chat-page platform-flow-ui",
) -> int:
    root = page.locator(chat_selector).first
    count = await root.evaluate("(el) => el.store.orderedTasks().length")
    if not isinstance(count, int):
        raise AssertionError(f"task count must be int, got {count!r}")
    return count


async def flows_chat_state_value(
    page: Page,
    path: str,
    *,
    chat_selector: str = "chat-page platform-flow-ui",
) -> Any:
    """Top-level field of the ``state`` artifact projection as seen by this client."""
    root = page.locator(chat_selector).first
    return await root.evaluate(
        "(el, path) => (Object.hasOwn(el.store.state, path) ? el.store.state[path] : null)",
        path,
    )


async def flows_chat_session_url(page: Page) -> str:
    await page.wait_for_url(re.compile(r"/flows/[^/]+/session/"), timeout=60_000)
    return page.url


@dataclass(frozen=True)
class FlowUIShareLink:
    share_url: str
    grant_id: str


async def flows_chat_create_share(
    page: Page,
    *,
    permission: str = "viewer",
    chat_selector: str = "chat-page platform-flow-ui",
    redacted_paths: list[str] | None = None,
) -> FlowUIShareLink:
    root = page.locator(chat_selector).first
    await expect(root).to_be_visible(timeout=30_000)
    paths = list(redacted_paths) if redacted_paths is not None else []
    if paths:
        payload = await root.evaluate(
            """async (el, args) => {
                if (typeof el.createShare !== 'function') {
                    throw new Error('platform-flow-ui.createShare missing');
                }
                return el.createShare({
                    permission: args.permission,
                    redactedPaths: args.paths,
                });
            }""",
            {"permission": permission, "paths": paths},
        )
        if not isinstance(payload, dict):
            raise AssertionError(f"share create returned non-object: {payload!r}")
        grant = payload.get("grant")
        if not isinstance(grant, dict) or not isinstance(grant.get("grant_id"), str):
            raise AssertionError(f"share create missing grant_id: {payload!r}")
        share_url = payload.get("share_url")
        if not isinstance(share_url, str) or "/l/" not in share_url:
            raise AssertionError(f"invalid share url: {share_url!r}")
        return FlowUIShareLink(share_url=share_url, grant_id=grant["grant_id"])

    share = root.locator("details.share").first
    await expect(share).to_be_visible(timeout=30_000)
    await share.locator("summary").click()
    label = "View only" if permission == "viewer" else "Can write"
    async with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and "/flows/api/v1/flow-ui/shares" in response.url
            and response.status < 400
        ),
        timeout=60_000,
    ) as share_response_info:
        await (
            share.locator("button")
            .filter(has_text=re.compile(rf"^\s*{re.escape(label)}\s*$"))
            .click()
        )
    share_response = await share_response_info.value
    payload = await share_response.json()
    grant = payload.get("grant")
    if not isinstance(grant, dict) or not isinstance(grant.get("grant_id"), str):
        raise AssertionError(f"share create missing grant_id: {payload!r}")
    grant_id = grant["grant_id"]
    link = share.locator('.share-result input[aria-label="Link"]')
    await expect(link).to_be_visible(timeout=60_000)
    share_url = await link.input_value()
    if not isinstance(share_url, str) or "/l/" not in share_url:
        raise AssertionError(f"invalid share url: {share_url!r}")
    return FlowUIShareLink(share_url=share_url, grant_id=grant_id)


async def flows_expire_share_grant(grant_id: str) -> None:
    """Mark grant expired in real flows DB (no mocks)."""
    database_url = os.environ.get("DATABASE__FLOWS_URL")
    if not isinstance(database_url, str) or database_url.strip() == "":
        raise AssertionError("DATABASE__FLOWS_URL required to expire Flow UI share grant")
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE flow_ui_share_grants "
                    "SET expires_at = NOW() - INTERVAL '1 minute' "
                    "WHERE grant_id = :grant_id AND revoked_at IS NULL"
                ),
                {"grant_id": grant_id},
            )
            if result.rowcount != 1:
                raise AssertionError(
                    f"flow_ui_share_grants expire updated {result.rowcount} rows "
                    f"for grant_id={grant_id!r}"
                )
    finally:
        await engine.dispose()


INTERFACE_PAGE_TAB_SELECTOR = 'flows-interface-pages-tabs .tab[role="tab"]'


async def flows_interface_add_page(page: Page) -> None:
    """Add a page in the Interface editor; waits until the tabs strip shows two pages."""
    editor = page.locator("flows-interface-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    tabs = editor.locator(INTERFACE_PAGE_TAB_SELECTOR)
    await expect(tabs).to_have_count(1, timeout=30_000)
    await expect(tabs.filter(has_text=re.compile(r"Conversation"))).to_be_visible(timeout=30_000)
    add = editor.locator("flows-interface-pages-tabs platform-button.add").first
    await expect(add).to_be_visible(timeout=10_000)
    await add.locator("button").first.click()
    await expect(tabs).to_have_count(2, timeout=30_000)
    await expect(tabs.filter(has_text=re.compile(r"New page|Новая страница"))).to_be_visible(
        timeout=15_000
    )


async def flows_interface_add_block(page: Page, label: str) -> None:
    """Insert a block from the Add panel by its palette label; selection follows the new block."""
    editor = page.locator("flows-interface-editor").first
    item = (
        editor.locator("flows-interface-add-panel article.item")
        .filter(has_text=re.compile(rf"^\s*{re.escape(label)}\s*$"))
        .first
    )
    await expect(item).to_be_visible(timeout=15_000)
    await item.click()


def flows_interface_canvas_block(page: Page, block_type: str) -> Locator:
    return page.locator(
        f'flows-interface-editor platform-flow-ui [data-block-id][data-block-type="{block_type}"]'
    )


async def flows_interface_publish(page: Page) -> None:
    """Publish from the shared editor header — the only Publish on Logic / Interface / Run."""
    await flows_publish_editor(page)
    await expect(
        page.locator("flows-editor-header .status-badge[data-status='dirty']")
    ).to_have_count(0, timeout=15_000)


async def flows_open_interface_editor_workspace(
    page: Page,
    flows_ui: AppUI,
    flow_id: str,
) -> None:
    await flows_open_editor(page, flows_ui, flow_id, layout="canvas")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=60_000)
    header = page.locator("flow-editor-page").locator("flows-editor-header").first
    await expect(header).to_be_visible(timeout=60_000)
    await flows_switch_editor_workspace(page, "interface")
    await expect(page.locator("flows-interface-editor")).to_be_visible(timeout=30_000)


async def flows_switch_editor_workspace(page: Page, workspace: str) -> None:
    if workspace not in {"logic", "interface", "run"}:
        raise ValueError(f"workspace must be logic|interface|run, got {workspace!r}")
    label = {"logic": "Logic", "interface": "Interface", "run": "Run"}[workspace]
    tab = (
        page.locator("flow-editor-page")
        .locator("flows-editor-header")
        .get_by_role("group", name=re.compile(r"Editor mode|Режим редактора"))
        .get_by_role("button", name=label, exact=True)
    )
    await expect(tab).to_be_visible(timeout=30_000)
    await tab.click()
    await expect(tab).to_have_attribute("data-active", "true", timeout=10_000)


async def flows_publish_editor(page: Page) -> None:
    await flows_close_floating_panel(page)
    await flows_dismiss_blocking_overlays(page)
    publish_pattern = re.compile(r"^\s*(?:Publish|Опубликовать)\s*$")
    button = (
        page.locator("flows-editor-header platform-button").filter(has_text=publish_pattern).first
    )
    await expect(button).to_be_visible(timeout=5_000)
    inner = button.locator("button").first
    await expect(inner).to_be_enabled(timeout=5_000)
    draft = (
        page.locator("flows-editor-header")
        .get_by_text(re.compile(r"^\s*(?:Draft|Черновик)\s*$"))
        .first
    )
    # Уже опубликовано и нет черновика — publish не шлёт PUT.
    if await draft.count() == 0:
        return
    try:
        async with page.expect_response(
            lambda response: (
                response.request.method == "PUT" and "/flows/api/v1/flows/" in response.url
            ),
            timeout=10_000,
        ) as publish_response:
            await button.evaluate("(el) => el.click()")
        response = await publish_response.value
    except TimeoutError as exc:
        if await draft.count() == 0 or not await draft.is_visible():
            return
        raise AssertionError(
            "flows_publish_editor: PUT /flows/api/v1/flows/ not observed while Draft visible"
        ) from exc
    if response.status >= 400:
        raise AssertionError(
            f"flows_publish_editor: PUT failed with {response.status}: {await response.text()}"
        )
    await expect(inner).to_be_enabled(timeout=5_000)


async def _flows_handle_post_drop_modal(page: Page, node_type: str) -> None:
    if node_type == "code":
        await flows_dismiss_code_node_drop_modal(page)
        return
    if node_type not in {"flow", "mcp"}:
        return
    picker = page.locator("flows-library-picker-modal").first
    if await picker.count() == 0:
        return
    if not await picker.is_visible():
        return
    card = picker.locator("platform-picker-card").first
    if await card.count() == 0:
        return
    if node_type == "mcp":
        await flows_pick_first_mcp_tool_in_picker(page)
        return
    await flows_pick_first_library_card(page)


async def flows_seed_mcp_store_catalog_entry(
    unique_id: str,
    *,
    upstream_url: str,
) -> str:
    """Глобальная catalog entry для UI/E2E MCP Store."""
    from tests.flows.integration.mcp_catalog_helpers import (
        build_verified_catalog_entry,
        persist_catalog_entry,
    )

    catalog_id = f"ui_doc_{unique_id}"
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=upstream_url,
        platform_approved=False,
        title=f"Doc MCP {unique_id}",
    )
    _ = await persist_catalog_entry(entry=entry)
    return catalog_id


async def flows_api_sync_mcp_server(
    origin: str,
    auth_token: str,
    server_id: str,
) -> None:
    async with _flows_client(origin, auth_token) as client:
        response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
    if response.status_code >= 400:
        raise AssertionError(
            f"POST /flows/api/v1/mcp/servers/{server_id}/sync failed: "
            f"{response.status_code} {response.text}"
        )


async def flows_open_mcp_servers_modal(page: Page) -> Locator:
    home = page.locator("flows-home-page").first
    await expect(home).to_be_visible(timeout=30_000)
    mcp_button = home.locator("platform-button").filter(has_text=re.compile(r"^\s*MCP\s*$", re.I))
    await expect(mcp_button.first).to_be_visible(timeout=30_000)
    await mcp_button.first.locator("button").first.click()
    modal = page.locator("flows-mcp-servers-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_drop_mcp_node(page: Page, *, x: int = 720, y: int = 420) -> None:
    """Открывает MCP tool picker через drop на канву (fallback через _applyPaletteDrop)."""
    canvas = page.locator("flows-flow-canvas").first
    await expect(canvas).to_be_visible(timeout=30_000)
    await canvas.evaluate(
        """
        (el, point) => {
            if (!el || typeof el._applyPaletteDrop !== 'function') {
                throw new Error('flows-flow-canvas._applyPaletteDrop is unavailable');
            }
            el._applyPaletteDrop({
                local: { x: point.x, y: point.y },
                nodeType: 'mcp',
                resourceType: '',
                htmlTargetNodeId: null,
            });
        }
        """,
        {"x": x, "y": y},
    )
    picker = page.locator("flows-library-picker-modal").first
    await expect(picker).to_be_visible(timeout=30_000)


async def flows_pick_first_mcp_tool_in_picker(page: Page) -> None:
    picker = page.locator("flows-library-picker-modal").first
    await expect(picker).to_be_visible(timeout=30_000)
    mcp_tab = picker.locator("platform-segmented-control").first
    if await mcp_tab.count() > 0:
        await flows_click_platform_button(picker, "MCP")
    card = picker.locator("platform-picker-card").first
    await expect(card).to_be_visible(timeout=30_000)
    await card.click()
    await expect(picker).to_be_hidden(timeout=30_000)


# --------------------------------------------------------------------------------------
# Сквозной пример «Зелёный сад» — единые значения имён/сущностей для всех сценариев.
# Только человекочитаемые подписи; технический жаргон в тексте инструкций запрещён.
# --------------------------------------------------------------------------------------

GREEN_GARDEN_STORE = "Зелёный сад"
GREEN_GARDEN_STORE_EN = "Green Garden"
GREEN_GARDEN_AGENT_NAME = "Помощник Зелёного сада"
GREEN_GARDEN_AGENT_NAME_EN = "Green Garden Assistant"
GREEN_GARDEN_RETURNS_AGENT = "Агент возвратов"
GREEN_GARDEN_RETURNS_AGENT_EN = "Returns Agent"
GREEN_GARDEN_BRANCH = "Летние скидки"
GREEN_GARDEN_BRANCH_EN = "Summer sale"
GREEN_GARDEN_CATALOG_FILE = "Каталог-весна-2026.pdf"
GREEN_GARDEN_DELIVERY_FILE = "Условия-доставки.pdf"
GREEN_GARDEN_SUPPORT_EMAIL = "support@zeleniy-sad.ru"
GREEN_GARDEN_WAREHOUSE_CITY = "Воронеж"
GREEN_GARDEN_TELEGRAM_BOT = "@zeleniy_sad_bot"
GREEN_GARDEN_ORDER_TRACKER = "Где мой заказ"
GREEN_GARDEN_SUPPORT_QUEUE = "Поддержка клиентов"
GREEN_GARDEN_RETURNS_QUEUE = "Возвраты"
GREEN_GARDEN_OPERATOR = "Марина"


def flows_background_task_payload(
    flow_id: str,
    *,
    name: str = GREEN_GARDEN_AGENT_NAME,
    queue_slug: str = "example_hitl",
    description: str = "",
) -> dict[str, Any]:
    """Минимальный flow с work_item_create (fire-and-forget) для HITL-документации."""
    return {
        "flow_id": flow_id,
        "name": name,
        "description": description,
        "entry": "agent",
        "nodes": {
            "agent": {
                "type": "llm_node",
                "name": "Agent",
                "prompt": (
                    "Ты помощник интернет-магазина «Зелёный сад». Если покупатель просит "
                    "перезвонить или проверить остаток на складе — создай фоновую задачу "
                    "через work_item_create в очередь "
                    f"{queue_slug} с blocking=false и сразу подтверди покупателю, что "
                    "запрос принят."
                ),
                "tools": ["work_item_create"],
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
        "tags": ["docs", "scenario", "hitl"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


# --------------------------------------------------------------------------------------
# Обобщённые операции с канвой редактора: drop любого типа ноды, wiring портов, условия.
# --------------------------------------------------------------------------------------


async def flows_dismiss_pwa_install_banner(page: Page) -> None:
    await ui_e2e_dismiss_pwa_install_banner(page)


def _flows_editor_layout_storage_key(flow_id: str) -> str:
    """Ключ localStorage как в apps/flows/ui/_helpers/flow-editor-layout.js."""
    segment = re.sub(r"[^a-z0-9_]+", "_", flow_id.lower())
    segment = re.sub(r"^_+|_+$", "", segment)
    segment = re.sub(r"_+", "_", segment)
    if not segment or not re.fullmatch(r"[a-z][a-z0-9_]*", segment):
        raise ValueError(f"Cannot derive editor_layout storage segment from flow_id={flow_id!r}")
    return f"platform:flows:editor_layout.{segment}"


async def flows_seed_editor_layout_preference(
    page: Page,
    flow_id: str,
    layout: Literal["agent", "canvas"],
) -> None:
    """Пишет preference до/после load — editor читает его при resolveEditorLayout."""
    if layout not in {"agent", "canvas"}:
        raise ValueError(f"layout must be agent|canvas, got {layout!r}")
    key = _flows_editor_layout_storage_key(flow_id)
    await page.evaluate(
        """([storageKey, value]) => { localStorage.setItem(storageKey, value); }""",
        [key, layout],
    )


async def flows_open_editor(
    page: Page,
    flows_ui: AppUI,
    flow_id: str,
    *,
    branch_id: str = "base",
    layout: Literal["agent", "canvas"] = "canvas",
) -> None:
    """Единая точка входа в редактор flow (Studio или канва)."""
    if layout not in {"agent", "canvas"}:
        raise ValueError(f"layout must be agent|canvas, got {layout!r}")
    if branch_id in {"", "base", "default"}:
        url = f"{flows_ui.origin}/flows/{flow_id}/editor"
    else:
        url = f"{flows_ui.origin}/flows/{flow_id}/editor/{branch_id}"
    layout_key = _flows_editor_layout_storage_key(flow_id)
    # add_init_script не принимает arg — значения вшиваем в исходник.
    # Дефолт E2E — канва; Agent Focus — layout="agent" или switch без reload.
    await page.add_init_script(
        f"""() => {{
            localStorage.setItem('pwa-banner-dismissed', 'true');
            localStorage.setItem({layout_key!r}, {layout!r});
            // Стабильные node_id в scenario (remote_partner, tracker, …) шарят prefs панели
            // между тестами в одном browser context — collapsed:true глушит editor slot.
            localStorage.removeItem('platform:flows:editor_property_panel_prefs');
        }}"""
    )
    await page.goto(url, wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=8_000)
    await flows_dismiss_pwa_install_banner(page)
    await expect(page.locator("flows-editor-header")).to_be_visible(timeout=8_000)
    if layout == "agent":
        studio = page.locator("flows-agent-focus-studio").first
        try:
            await expect(studio).to_be_visible(timeout=8_000)
        except AssertionError:
            await flows_e2e_switch_editor_layout(page, "agent")
            await expect(studio).to_be_visible(timeout=8_000)
        # Studio shell ≠ готовность branchData: ждём llm editor, иначе ветки flake.
        llm_editor = studio.locator("flows-llm-node-editor").first
        try:
            await expect(llm_editor).to_be_visible(timeout=8_000)
        except AssertionError:
            await flows_e2e_switch_editor_layout(page, "agent")
            await expect(llm_editor).to_be_visible(timeout=8_000)
        return
    # LLM-графы могут открыться в Agent Focus несмотря на localStorage=canvas —
    # переключаем и ждём branchData с короткими ретраями (late setFlow / flip-back).
    last_error: BaseException | None = None
    for _attempt in range(4):
        try:
            await flows_e2e_ensure_canvas_layout(page)
            await expect(page.locator("flows-flow-canvas svg.canvas-host").first).to_be_visible(
                timeout=3_000
            )
            await _flows_wait_branch_data_ready(page, timeout_s=2.5)
            return
        except (AssertionError, PlaywrightTimeoutError) as exc:
            last_error = exc
            await asyncio.sleep(0.25)
    if last_error is not None:
        raise AssertionError("flows_open_editor: canvas branchData not ready") from last_error
    raise AssertionError("flows_open_editor: canvas branchData not ready")


async def flows_canvas_node_ids_of_type(page: Page, node_type: str) -> list[str]:
    """ID нод данного type из branchData (SVG data-* атрибуты могут отставать)."""
    canvas = page.locator("flows-flow-canvas").first
    raw = await canvas.evaluate(
        """
        (el, wantedType) => {
            if (!el || typeof el._branchData !== 'function') {
                return [];
            }
            const data = el._branchData();
            const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            return Object.entries(nodes)
                .filter(([, node]) => node && typeof node === 'object' && node.type === wantedType)
                .map(([nodeId]) => nodeId);
        }
        """,
        node_type,
    )
    if not isinstance(raw, list):
        raise AssertionError(f"flows_canvas_node_ids_of_type: unexpected payload {raw!r}")
    return [str(node_id) for node_id in raw if isinstance(node_id, str) and node_id]


async def flows_dismiss_code_node_drop_modal(page: Page) -> None:
    """Закрывает модалку выбора шаблона после дропа code-ноды (пустая нода)."""
    modal = page.locator("flows-code-node-drop-modal").first
    if await modal.count() == 0:
        return
    if not await modal.is_visible():
        return
    blank = (
        modal.locator("platform-picker-card")
        .filter(has_text=re.compile(r"Empty node|Пустая нода", re.I))
        .first
    )
    await expect(blank).to_be_visible(timeout=15_000)
    await blank.evaluate(
        """
        (el) => {
            el.dispatchEvent(
                new CustomEvent('select', {
                    detail: { value: el.value || 'blank' },
                    bubbles: true,
                    composed: true,
                })
            );
        }
        """
    )
    await expect(modal).to_be_hidden(timeout=15_000)


async def _flows_apply_palette_drop(
    page: Page,
    *,
    node_type: str,
    x: int,
    y: int,
    resource_type: str,
) -> None:
    canvas = page.locator("flows-flow-canvas").first
    await canvas.evaluate(
        """
        (el, ctx) => {
            if (!el || typeof el._applyPaletteDrop !== 'function') {
                throw new Error('flows-flow-canvas._applyPaletteDrop is unavailable');
            }
            el._applyPaletteDrop({
                local: { x: ctx.x, y: ctx.y },
                nodeType: ctx.nodeType,
                resourceType: ctx.resourceType,
                htmlTargetNodeId: null,
            });
        }
        """,
        {"x": x, "y": y, "nodeType": node_type, "resourceType": resource_type},
    )


async def _flows_wait_branch_data_ready(page: Page, *, timeout_s: float = 5.0) -> None:
    canvas = page.locator("flows-flow-canvas").first
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await canvas.count() == 0:
            await asyncio.sleep(0.1)
            continue
        try:
            ready = await canvas.evaluate(
                """
                (el) => {
                    if (!el || typeof el._branchData !== 'function') return false;
                    const data = el._branchData();
                    const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
                    return Object.keys(nodes).length > 0;
                }
                """,
                timeout=1_000,
            )
        except TimeoutError, PlaywrightTimeoutError:
            await asyncio.sleep(0.1)
            continue
        if ready is True:
            return
        await asyncio.sleep(0.1)
    raise AssertionError("flows canvas branchData empty after wait")


async def flows_drop_node(
    page: Page,
    node_type: str,
    *,
    x: int = 700,
    y: int = 330,
    resource_type: str = "",
) -> str:
    """Добавляет ноду в branchData (palette drop + fallback inject)."""
    await flows_e2e_ensure_canvas_layout(page)
    await flows_dismiss_blocking_overlays(page)
    canvas = page.locator("flows-flow-canvas").first
    await expect(page.locator("flows-flow-canvas svg.canvas-host").first).to_be_visible(
        timeout=5_000
    )
    await _flows_wait_branch_data_ready(page)
    before_ids = set(await flows_canvas_node_ids_of_type(page, node_type))

    if node_type in {"flow", "mcp", "reflection"}:
        await _flows_apply_palette_drop(
            page,
            node_type=node_type,
            x=x,
            y=y,
            resource_type=resource_type,
        )
        await _flows_handle_post_drop_modal(page, node_type)
    else:
        # Прямой inject: _applyPaletteDrop для llm/channel кладёт config:{} и UI может
        # не материализовать ноду стабильно для E2E. Повтор при race с late load.
        inject_js = """
            (el, ctx) => {
                if (!el || !el._editor || typeof el._branchData !== 'function') {
                    throw new Error('flows-flow-canvas editor state is unavailable');
                }
                const data = el._branchData();
                const nodeId = `n_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
                const base = {
                    type: ctx.nodeType,
                    name: ctx.nodeType,
                    pos_x: ctx.x - 140,
                    pos_y: ctx.y - 40,
                };
                let node = base;
                if (ctx.nodeType === 'llm_node') {
                    node = {
                        ...base,
                        prompt: 'Отвечай кратко.',
                        tools: [],
                        agent_skills: [],
                        llm: {
                            provider: 'humanitec_llm',
                            model: 'auto',
                            temperature: 0.2,
                            max_tokens: 1024,
                        },
                    };
                } else if (ctx.nodeType === 'channel') {
                    node = {
                        ...base,
                        channel: 'telegram',
                        action: 'send_message',
                        channel_config: {},
                    };
                } else if (ctx.nodeType === 'external_api') {
                    node = {
                        ...base,
                        method: 'GET',
                        url: 'https://httpbin.org/get',
                        headers: {},
                        timeout: 30,
                    };
                } else if (ctx.nodeType === 'code') {
                    node = {
                        ...base,
                        language: 'python',
                        code: ctx.code || '',
                    };
                } else if (ctx.nodeType === 'code_agent') {
                    node = {
                        ...base,
                        language: 'python',
                        invoke_kind: 'cli',
                    };
                }
                const nodes = { ...(data.nodes || {}), [nodeId]: node };
                const next = { ...data, nodes };
                el._editor.updateBranchData({ data: next });
                el._editor.pushHistory({ snapshot: next });
                el._editor.setDirty({ dirty: true });
                el._editor.selectNode({ nodeId });
                return nodeId;
            }
        """
        inject_ctx: dict[str, Any] = {"x": x, "y": y, "nodeType": node_type}
        if node_type == "code":
            inject_ctx["code"] = (
                "async def run(args, state):\n"
                '    state["response"] = state.get("content", "")\n'
                "    return state\n"
            )
        injected = ""
        for _attempt in range(5):
            candidate = await canvas.evaluate(inject_js, inject_ctx)
            if not isinstance(candidate, str) or not candidate:
                await asyncio.sleep(0.15)
                continue
            present_deadline = time.monotonic() + 2.0
            while time.monotonic() < present_deadline:
                present = await canvas.evaluate(
                    """
                    (el, selectedNodeId) => {
                        const data = el._branchData();
                        return Boolean(data && data.nodes && data.nodes[selectedNodeId]);
                    }
                    """,
                    candidate,
                )
                if present is True:
                    # Late GET flow может перезаписать branchData сразу после inject.
                    await asyncio.sleep(0.35)
                    still = await canvas.evaluate(
                        """
                        (el, selectedNodeId) => {
                            const data = el._branchData();
                            return Boolean(data && data.nodes && data.nodes[selectedNodeId]);
                        }
                        """,
                        candidate,
                    )
                    if still is True:
                        if node_type == "code_agent":
                            await canvas.evaluate(
                                """
                                (el, selectedNodeId) => {
                                    if (typeof el._ensureCodeAgentSource !== 'function') {
                                        throw new Error('flows-flow-canvas: _ensureCodeAgentSource required');
                                    }
                                    return el._ensureCodeAgentSource(selectedNodeId);
                                }
                                """,
                                candidate,
                            )
                        return candidate
                    break
                await asyncio.sleep(0.1)
            injected = candidate
        raise AssertionError(
            f"flows_drop_node({node_type!r}): inject not sticky in branchData (last={injected!r})"
        )

    seed_node_ids = frozenset({"start", "end", "agent", "entry", "orchestrator", "echo"})
    timeout_seconds = 8.0 if node_type in {"flow", "mcp"} else 5.0
    deadline = time.monotonic() + timeout_seconds
    node_id = ""
    while time.monotonic() < deadline:
        await _flows_handle_post_drop_modal(page, node_type)
        after_ids = set(await flows_canvas_node_ids_of_type(page, node_type))
        new_ids = sorted(after_ids - before_ids)
        if len(new_ids) != 1:
            filtered = [candidate for candidate in new_ids if candidate not in seed_node_ids]
            if len(filtered) == 1:
                new_ids = filtered
        if len(new_ids) == 1:
            node_id = new_ids[0]
            break
        await asyncio.sleep(0.2)

    if not node_id:
        timeout_label = "8s" if node_type in {"flow", "mcp"} else "5s"
        raise AssertionError(
            f"flows_drop_node({node_type!r}): no new node appeared within {timeout_label} "
            f"(before={sorted(before_ids)!r})"
        )
    return node_id


async def flows_select_canvas_node(page: Page, node_id: str) -> None:
    """Выбирает ноду через editor.selectNode (SVG data-node-id может отставать)."""
    await flows_e2e_ensure_canvas_layout(page)
    canvas = page.locator("flows-flow-canvas").first
    await expect(canvas).to_be_visible(timeout=5_000)
    await canvas.evaluate(
        """
        (el, selectedNodeId) => {
            if (!el || !el._editor || typeof el._editor.selectNode !== 'function') {
                throw new Error('flows-flow-canvas.selectNode unavailable');
            }
            if (typeof el._branchData === 'function') {
                const data = el._branchData();
                const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
                if (!Object.prototype.hasOwnProperty.call(nodes, selectedNodeId)) {
                    throw new Error(`node ${selectedNodeId} missing in branchData`);
                }
            }
            el._editor.selectNode({ nodeId: selectedNodeId });
        }
        """,
        node_id,
    )
    node = page.locator(f"flows-flow-canvas g.node[data-node-id='{node_id}']").first
    if await node.count() > 0 and await node.is_visible():
        await node.dblclick(force=True)


async def flows_canvas_node_ids(page: Page) -> list[str]:
    """Список node_id всех нод из branchData."""
    canvas = page.locator("flows-flow-canvas").first
    raw = await canvas.evaluate(
        """
        (el) => {
            if (!el || typeof el._branchData !== 'function') {
                return [];
            }
            const data = el._branchData();
            const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            return Object.keys(nodes);
        }
        """
    )
    if not isinstance(raw, list):
        raise AssertionError(f"flows_canvas_node_ids: unexpected payload {raw!r}")
    return [str(node_id) for node_id in raw if isinstance(node_id, str) and node_id]


async def flows_canvas_edge_count(page: Page) -> int:
    return await page.locator("flows-flow-canvas g.edge-group, flows-flow-canvas path.edge").count()


async def flows_canvas_has_edge(page: Page, from_node_id: str, to_node_id: str) -> bool:
    """Есть ли control-flow ребро в branchData (DOM edges могут отставать)."""
    canvas = page.locator("flows-flow-canvas").first
    found = await canvas.evaluate(
        """
        (el, ctx) => {
            if (!el || typeof el._branchData !== 'function') return false;
            const data = el._branchData();
            const edges = Array.isArray(data && data.edges) ? data.edges : [];
            return edges.some(
                (edge) => edge
                    && edge.from_node === ctx.fromNode
                    && edge.to_node === ctx.toNode
            );
        }
        """,
        {"fromNode": from_node_id, "toNode": to_node_id},
    )
    return found is True


async def flows_wire_ports(page: Page, from_node_id: str, to_node_id: str) -> None:
    """Протягивает control-flow связь из out-порта одной ноды в in-порт другой.

    Использует реальные pointer-события; при неудаче — детерминированный fallback
    через тот же путь, что и pointerup канвы (append edge + setDirty).
    """
    await flows_close_floating_panel(page)
    if await flows_canvas_has_edge(page, from_node_id, to_node_id):
        return
    out_port = page.locator(
        f"flows-flow-canvas .port[data-port-side='out'][data-node-id='{from_node_id}']"
    ).first
    in_port = page.locator(
        f"flows-flow-canvas .port[data-port-side='in'][data-node-id='{to_node_id}']"
    ).first
    ports_visible = False
    try:
        await expect(out_port).to_be_visible(timeout=1_000)
        await expect(in_port).to_be_visible(timeout=1_000)
        ports_visible = True
    except AssertionError:
        pass

    before = await flows_canvas_edge_count(page)
    out_box = None
    in_box = None
    if ports_visible:
        try:
            out_box = await out_port.bounding_box(timeout=2_000)
            in_box = await in_port.bounding_box(timeout=2_000)
        except PlaywrightTimeoutError:
            out_box = None
            in_box = None
    if out_box and in_box:
        ox = out_box["x"] + out_box["width"] / 2
        oy = out_box["y"] + out_box["height"] / 2
        ix = in_box["x"] + in_box["width"] / 2
        iy = in_box["y"] + in_box["height"] / 2
        await page.mouse.move(ox, oy)
        await page.mouse.down()
        await page.mouse.move((ox + ix) / 2, (oy + iy) / 2, steps=6)
        await page.mouse.move(ix, iy, steps=6)
        await page.mouse.up()

    try:
        await expect(
            page.locator("flows-flow-canvas g.edge-group, flows-flow-canvas path.edge")
        ).to_have_count(
            before + 1,
            timeout=3_000,
        )
        if await flows_canvas_has_edge(page, from_node_id, to_node_id):
            return
    except AssertionError:
        pass

    await page.locator("flows-flow-canvas").evaluate(
        """
        (el, ctx) => {
            const data = el._branchData();
            const edges = Array.isArray(data.edges) ? [...data.edges] : [];
            const exists = edges.some(
                (edge) => edge
                    && edge.from_node === ctx.fromNode
                    && edge.to_node === ctx.toNode
            );
            if (!exists) {
                edges.push({ from_node: ctx.fromNode, to_node: ctx.toNode });
            }
            const next = { ...data, edges };
            el._editor.updateBranchData({ data: next });
            el._editor.pushHistory({ snapshot: next });
            el._editor.setDirty({ dirty: true });
        }
        """,
        {"fromNode": from_node_id, "toNode": to_node_id},
    )
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if await flows_canvas_has_edge(page, from_node_id, to_node_id):
            return
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"flows_wire_ports: edge {from_node_id!r}->{to_node_id!r} missing in branchData"
    )


async def flows_dismiss_blocking_overlays(page: Page) -> None:
    await flows_dismiss_pwa_install_banner(page)
    await page.evaluate(
        """
        () => {
            document.querySelectorAll('glass-toast').forEach((toast) => toast.remove());
        }
        """
    )
    for selector in ("flows-variable-editor-modal", "flows-variables-modal"):
        modal = page.locator(selector).first
        if await modal.count() == 0:
            continue
        if not await modal.is_visible():
            continue
        await page.keyboard.press("Escape")
        try:
            await expect(modal).to_be_hidden(timeout=5_000)
        except AssertionError:
            await modal.evaluate("(el) => { if (typeof el.close === 'function') el.close(); }")


async def flows_close_floating_panel(page: Page) -> None:
    """Закрывает открытую floating-панель редактора ноды, если она перекрывает канву."""
    await flows_dismiss_blocking_overlays(page)
    panel = page.locator("flows-floating-panel").first
    if await panel.count() == 0:
        return
    if not await panel.is_visible():
        return
    close_button = panel.locator(
        'platform-button[aria-label*="close" i], platform-button[aria-label*="Закрыть"]'
    ).first
    if await close_button.count() > 0:
        await close_button.evaluate("(el) => el.click()")
    else:
        await page.keyboard.press("Escape")
    try:
        await expect(panel).to_be_hidden(timeout=5_000)
    except AssertionError:
        pass


async def flows_wait_node_in_branch_data(
    page: Page,
    node_id: str,
    *,
    timeout_s: float = 15.0,
) -> None:
    """Ждёт появления node_id в branchData (после load flow)."""
    canvas = page.locator("flows-flow-canvas").first
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        present = await canvas.evaluate(
            """
            (el, selectedNodeId) => {
                if (!el || typeof el._branchData !== 'function') return false;
                const data = el._branchData();
                const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
                return Object.prototype.hasOwnProperty.call(nodes, selectedNodeId);
            }
            """,
            node_id,
        )
        if present is True:
            return
        await asyncio.sleep(0.1)
    keys = await flows_canvas_node_ids(page)
    raise AssertionError(
        f"flows_wait_node_in_branch_data: {node_id!r} missing after {timeout_s}s (nodes={keys!r})"
    )


async def _flows_expand_collapsed_node_panel(page: Page, node_id: str) -> None:
    """Если floating-панель ноды свернута — восстанавливает (иначе editor slot пуст)."""
    collapsed = page.locator(f"flows-floating-panel[panel-id='{node_id}'][data-collapsed]").first
    if await collapsed.count() == 0 or not await collapsed.is_visible():
        return
    restore = collapsed.locator(
        'platform-button[aria-label*="restore" i], '
        'platform-button[aria-label*="Restore" i], '
        'platform-button[aria-label*="Развернуть"], '
        'platform-button[aria-label*="восстанов"]'
    ).first
    if await restore.count() > 0:
        await restore.evaluate("(el) => el.click()")
    else:
        await page.locator("flows-flow-canvas").first.evaluate(
            """
            (el, selectedNodeId) => {
                if (!el || !el._editor || typeof el._editor.selectNode !== 'function') {
                    throw new Error('flows-flow-canvas.selectNode unavailable');
                }
                el._editor.selectNode({ nodeId: selectedNodeId });
                if (typeof el._editor.setPropertyPanelLayout === 'function') {
                    el._editor.setPropertyPanelLayout({
                        nodeId: selectedNodeId,
                        layout: { collapsed: false },
                    });
                }
            }
            """,
            node_id,
        )
    await expect(
        page.locator(f"flows-floating-panel[panel-id='{node_id}'][show-backdrop]").first
    ).to_be_visible(timeout=5_000)


async def flows_open_node_editor(page: Page, node_id: str) -> Locator:
    """Открывает редактор ноды: Agent Focus studio или floating-панель на канве."""
    await flows_dismiss_blocking_overlays(page)
    studio = page.locator("flows-agent-focus-studio").first
    if await studio.count() > 0 and await studio.is_visible():
        # Studio — только для single llm_node; reflection/другие ноды — через canvas.
        studio_node = await studio.evaluate(
            """
            (el) => {
                if (typeof el._soleNodeId === 'function') {
                    try {
                        const sole = el._soleNodeId();
                        if (typeof sole === 'string') return sole;
                    } catch (_err) {
                        return '';
                    }
                }
                if (typeof el.nodeId === 'string') return el.nodeId;
                return '';
            }
            """
        )
        if studio_node == node_id:
            llm_editor = studio.locator("flows-llm-node-editor").first
            await expect(llm_editor).to_be_visible(timeout=5_000)
            return studio
        if studio_node:
            # Studio на другом sole-node (llm vs reflection) — нужен canvas.
            await flows_e2e_ensure_canvas_layout(page)
        else:
            # branchData ещё не готов: _soleNodeId бросает → пустая строка.
            # Нельзя сразу flip в canvas — ломает Agent Focus сценарии веток.
            llm_editor = studio.locator("flows-llm-node-editor").first
            try:
                await expect(llm_editor).to_be_visible(timeout=8_000)
                return studio
            except AssertionError:
                await flows_e2e_ensure_canvas_layout(page)

    await flows_e2e_ensure_canvas_layout(page)
    await flows_wait_node_in_branch_data(page, node_id)
    floating = page.locator(f"flows-floating-panel[panel-id='{node_id}'][show-backdrop]").first
    node_editor = floating.locator(
        "flows-llm-node-editor, "
        "flows-reflection-node-editor, "
        "flows-code-node-editor, "
        "flows-code-agent-editor, "
        "flows-remote-flow-editor, "
        "flows-channel-node-editor, "
        "flows-external-api-editor, "
        "flows-mcp-node-editor, "
        "flows-hitl-node-editor, "
        "flows-resource-node-editor, "
        "flows-base-node-editor"
    ).first
    if await floating.count() > 0 and await floating.is_visible() and await node_editor.count() > 0:
        await expect(node_editor).to_be_visible(timeout=2_000)
        return floating
    await flows_close_floating_panel(page)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        await flows_select_canvas_node(page, node_id)
        await _flows_expand_collapsed_node_panel(page, node_id)
        await asyncio.sleep(0.15)
        if (
            await floating.count() > 0
            and await floating.is_visible()
            and await node_editor.count() > 0
            and await node_editor.is_visible()
        ):
            return floating
    await expect(floating).to_be_visible(timeout=5_000)
    await expect(node_editor).to_be_visible(timeout=5_000)
    return floating


async def flows_toggle_data_wires(page: Page) -> None:
    await flows_e2e_ensure_canvas_layout(page)
    await flows_dismiss_blocking_overlays(page)
    await flows_close_floating_panel(page)
    wires_btn = (
        page.locator("flows-bottom-toolbar platform-button")
        .filter(has=page.locator("platform-icon[name='link']"))
        .first
    )
    await expect(wires_btn).to_be_visible(timeout=5_000)
    await wires_btn.evaluate("(el) => el.click()")


async def flows_open_problems(page: Page) -> Locator:
    button = page.locator(
        "flows-flow-canvas .problems-btn, flows-bottom-toolbar .problems-btn"
    ).first
    await expect(button).to_be_visible(timeout=15_000)
    await button.click()
    flyout = page.locator(".problems-flyout, flows-dataflow-problems").first
    await expect(flyout).to_be_visible(timeout=15_000)
    return flyout


async def flows_seed_mock_llm(responses: list[Any]) -> None:
    """Предзасев MockLLM под worker E2E-scope (см. tests/ui/e2e_worker.py)."""
    from core.clients.llm.mock import setup_mock_responses_redis
    from core.clients.redis_client import RedisClient
    from core.config import get_settings
    from tests.ui.e2e_worker import ui_e2e_test_scope

    redis_client = RedisClient(get_settings().database.redis_url)
    try:
        await setup_mock_responses_redis(
            redis_client,
            responses,
            test_scope=ui_e2e_test_scope(),
        )
    finally:
        await redis_client.close()


# --------------------------------------------------------------------------------------
# Dataflow seed payloads (merge legacy dataflow-wiring + dataflow-problems scenarios).
# --------------------------------------------------------------------------------------


def flows_dataflow_broken_payload(flow_id: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": "Dataflow wiring E2E",
        "description": "Code produces topic, LLM requires topic via prompt",
        "entry": "code_1",
        "nodes": {
            "code_1": {
                "type": "code",
                "name": "Code",
                "language": "python",
                "code": ("async def run(args, state):\n    state['topic'] = 'ai'\n    return {}\n"),
                "pos_x": 0,
                "pos_y": 0,
            },
            "llm_1": {
                "type": "llm_node",
                "name": "LLM",
                "prompt": "Summarize {topic}",
                "pos_x": 320,
                "pos_y": 0,
            },
        },
        "edges": [{"from_node": "code_1", "to_node": "llm_1"}],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_dataflow_problems_payload(flow_id: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": "Dataflow problems E2E",
        "description": "LLM prompt requires undeclared variable",
        "entry": "llm_1",
        "nodes": {
            "llm_1": {
                "type": "llm_node",
                "name": "Broken LLM",
                "prompt": "Explain {missing_topic}",
                "pos_x": 0,
                "pos_y": 0,
            },
        },
        "edges": [{"from_node": "llm_1", "to_node": None}],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_branch_condition_payload(flow_id: str, *, name: str) -> dict[str, Any]:
    """Граф с двумя ветками после code-ноды для сценария edge condition."""
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "Branch by keyword condition",
        "entry": "router",
        "nodes": {
            "router": {
                "type": "code",
                "name": "Router",
                "language": "python",
                "code": (
                    "async def run(args, state):\n"
                    "    content = str(state.get('content', '')).lower()\n"
                    "    state['intent'] = 'returns' if 'возврат' in content else 'order'\n"
                    "    return state\n"
                ),
                "pos_x": 0,
                "pos_y": 0,
            },
            "order_path": {
                "type": "code",
                "name": "Order",
                "language": "python",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = 'order-path'\n"
                    "    return state\n"
                ),
                "pos_x": 320,
                "pos_y": -80,
            },
            "returns_path": {
                "type": "code",
                "name": "Returns",
                "language": "python",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = 'returns-path'\n"
                    "    return state\n"
                ),
                "pos_x": 320,
                "pos_y": 80,
            },
        },
        "edges": [
            {
                "from_node": "router",
                "to_node": "order_path",
                "condition": {
                    "type": "simple",
                    "variable": "intent",
                    "operator": "==",
                    "value": "order",
                },
            },
            {
                "from_node": "router",
                "to_node": "returns_path",
                "condition": {
                    "type": "simple",
                    "variable": "intent",
                    "operator": "==",
                    "value": "returns",
                },
            },
        ],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


# --------------------------------------------------------------------------------------
# Editor run panel, edge conditions, problems, sticky notes.
# --------------------------------------------------------------------------------------


async def flows_switch_editor_mode(page: Page, mode: Literal["edit", "run"]) -> None:
    header = page.locator("flows-editor-header").first
    await expect(header).to_be_visible(timeout=30_000)
    group = header.get_by_role("group", name=re.compile(r"Editor mode|Режим"))
    if mode == "run":
        btn = group.get_by_role("button", name=re.compile(r"^Run$|Запуск"))
    else:
        btn = group.get_by_role("button", name=re.compile(r"Visual editor|Визуальный"))
    await expect(btn).to_be_visible(timeout=15_000)
    if await btn.get_attribute("aria-pressed") != "true":
        await btn.click()
    if mode == "run":
        panel = page.locator("flows-execution-panel:not([data-panel-closed])").first
        await expect(panel).to_be_visible(timeout=15_000)


async def flows_open_execution_panel(page: Page) -> Locator:
    await flows_switch_editor_mode(page, "run")
    panel = page.locator("flows-execution-panel").first
    await expect(panel).to_be_visible(timeout=15_000)
    return panel


async def flows_execution_send_message(page: Page, text: str) -> None:
    panel = await flows_open_execution_panel(page)
    chat = panel.locator("platform-flow-ui").first
    await expect(chat).to_be_visible(timeout=15_000)
    textarea = chat.locator(FLOW_UI_COMPOSER_SELECTOR).first
    await expect(textarea).to_be_visible(timeout=15_000)
    await textarea.fill(text)
    send_btn = chat.get_by_role("button", name=FLOW_UI_SEND_PATTERN).first
    await expect(send_btn).to_be_enabled(timeout=10_000)
    await send_btn.click()


async def flows_click_edge_label(page: Page, edge_index: int = 0) -> None:
    label = page.locator("flows-flow-canvas g.edge-group .edge-label").nth(edge_index)
    await expect(label).to_be_visible(timeout=5_000)
    await label.evaluate("(el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true }))")


async def flows_open_edge_condition_modal(page: Page, *, edge_index: int = 0) -> Locator:
    """Открывает модалку условия; без label — через openModal канвы."""
    await flows_e2e_ensure_canvas_layout(page)
    await flows_dismiss_blocking_overlays(page)
    labels = page.locator("flows-flow-canvas g.edge-group .edge-label")
    if await labels.count() > edge_index:
        await flows_click_edge_label(page, edge_index)
    else:
        canvas = page.locator("flows-flow-canvas").first
        await canvas.evaluate(
            """
            (el, idx) => {
                if (typeof el.openModal !== 'function') {
                    throw new Error('flows-flow-canvas.openModal unavailable');
                }
                el.openModal('flows.edge_condition', { edgeIndex: idx });
            }
            """,
            edge_index,
        )
    modal = page.locator("flows-edge-condition-modal").first
    await expect(modal).to_be_visible(timeout=5_000)
    return modal


async def flows_set_edge_condition_simple(
    page: Page,
    *,
    variable: str,
    operator: str,
    value: str,
    edge_index: int | None = None,
    to_node: str | None = None,
) -> None:
    """Пишет simple-condition в branchData (модалка platform-field enum нестабильна в E2E)."""
    if to_node is None and edge_index is None:
        raise ValueError("flows_set_edge_condition_simple: to_node or edge_index required")
    await flows_e2e_ensure_canvas_layout(page)
    await _flows_wait_branch_data_ready(page, timeout_s=5.0)
    canvas = page.locator("flows-flow-canvas").first
    await expect(canvas).to_be_visible(timeout=5_000)
    inject_ctx = {
        "edgeIndex": edge_index,
        "toNode": to_node,
        "variable": variable,
        "operator": operator,
        "value": value,
    }
    inject_js = """
        (el, ctx) => {
            if (!el || !el._editor || typeof el._branchData !== 'function') {
                throw new Error('flows-flow-canvas editor state is unavailable');
            }
            const data = el._branchData();
            const edges = Array.isArray(data.edges) ? [...data.edges] : [];
            let edgeIndex = typeof ctx.edgeIndex === 'number' ? ctx.edgeIndex : -1;
            if (typeof ctx.toNode === 'string' && ctx.toNode.length > 0) {
                edgeIndex = edges.findIndex((edge) => edge && edge.to_node === ctx.toNode);
            }
            if (edgeIndex < 0 || edgeIndex >= edges.length) {
                throw new Error(
                    `edge not found (to_node=${ctx.toNode}, edge_index=${ctx.edgeIndex}, edges=${edges.length})`
                );
            }
            edges[edgeIndex] = {
                ...edges[edgeIndex],
                condition: {
                    type: 'simple',
                    variable: ctx.variable,
                    operator: ctx.operator,
                    value: ctx.value,
                },
            };
            const next = { ...data, edges };
            el._editor.updateBranchData({ data: next });
            el._editor.setDirty({ dirty: true });
            el._editor.pushHistory({ snapshot: next });
            return edgeIndex;
        }
    """
    verify_js = """
        (el, ctx) => {
            if (!el || typeof el._branchData !== 'function') return null;
            const data = el._branchData();
            const edges = Array.isArray(data.edges) ? data.edges : [];
            const edge = typeof ctx.toNode === 'string' && ctx.toNode.length > 0
                ? edges.find((item) => item && item.to_node === ctx.toNode)
                : edges[ctx.edgeIndex];
            if (!edge || !edge.condition || typeof edge.condition !== 'object') return null;
            return edge.condition.value;
        }
    """
    for _attempt in range(3):
        await canvas.evaluate(inject_js, inject_ctx)
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            current = await canvas.evaluate(verify_js, inject_ctx)
            if current == value:
                return
            await asyncio.sleep(0.1)
    raise AssertionError(
        f"flows_set_edge_condition_simple: condition value {value!r} not sticky "
        f"(to_node={to_node!r}, edge_index={edge_index!r})"
    )


async def flows_save_edge_condition_modal(page: Page) -> None:
    modal = page.locator("flows-edge-condition-modal").first
    await flows_click_platform_button(modal, "Сохранить", "Save")
    await expect(modal).to_be_hidden(timeout=15_000)


async def flows_open_incoming_policy_modal(page: Page, node_id: str) -> Locator:
    node = page.locator(f"flows-flow-canvas g.node[data-node-id='{node_id}']").first
    await expect(node).to_be_visible(timeout=15_000)
    await node.dblclick()
    modal = page.locator("flows-incoming-policy-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_set_incoming_policy(page: Page, policy: Literal["any", "all"]) -> None:
    modal = page.locator("flows-incoming-policy-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    option = modal.locator(f"[data-policy='{policy}'], button[data-value='{policy}']").first
    if await option.count() > 0:
        await option.click()
    else:
        await modal.evaluate(
            """
            (el, policy) => {
                el._policy = policy;
                if (typeof el.requestUpdate === 'function') el.requestUpdate();
            }
            """,
            policy,
        )
    await flows_click_platform_button(modal, "Сохранить", "Save")
    await expect(modal).to_be_hidden(timeout=15_000)


async def flows_open_problems_flyout(page: Page) -> Locator:
    await page.wait_for_function(
        """
        () => {
            const canvas = document.querySelector('flows-flow-canvas');
            const state = canvas && canvas._editor ? canvas._editor.state : null;
            const nodes = state && state.dataflow && state.dataflow.nodes;
            if (!nodes) return false;
            return Object.values(nodes).some(
                (info) => info && Array.isArray(info.issues) && info.issues.length > 0
            );
        }
        """,
        timeout=30_000,
    )
    btn = page.locator("flows-editor-header .problems-btn").first
    await expect(btn).to_be_visible(timeout=15_000)
    await btn.evaluate("(el) => el.click()")
    flyout = page.locator(".flows-editor-header-menu-portal.problems-flyout").first
    try:
        await expect(flyout).to_be_visible(timeout=5_000)
        return flyout
    except AssertionError:
        return await flows_open_problems(page)


async def flows_click_problem_item(page: Page, index: int = 0) -> None:
    await flows_open_problems_flyout(page)
    item = page.locator("flows-editor-header .problem-item").nth(index)
    await expect(item).to_be_visible(timeout=15_000)
    await item.click()


async def flows_assert_problems_count(page: Page, expected: int) -> None:
    btn = page.locator("flows-editor-header .problems-btn").first
    await expect(btn).to_be_visible(timeout=15_000)
    if expected == 0:
        await expect(btn).to_have_count(0)
        return
    count_el = btn.locator(".problems-count")
    await expect(count_el).to_have_text(str(expected), timeout=15_000)


async def flows_assert_selected_node(page: Page, node_id: str) -> None:
    selected = page.locator(f"flows-flow-canvas g.node.selected[data-node-id='{node_id}']").first
    await expect(selected).to_be_visible(timeout=15_000)


async def flows_add_sticky_note(page: Page, text: str) -> None:
    await flows_e2e_ensure_canvas_layout(page)
    canvas = page.locator("flows-flow-canvas").first
    await canvas.evaluate(
        """
        (el, noteText) => {
            if (typeof el._addStickyNoteAtCenter !== 'function') {
                throw new Error('flows-flow-canvas._addStickyNoteAtCenter is unavailable');
            }
            el._addStickyNoteAtCenter();
            const notes = el._state().stickyNotes;
            const last = notes[notes.length - 1];
            if (last) {
                el._editor.updateStickyNote({ note: { ...last, text: noteText } });
            }
        }
        """,
        text,
    )


async def flows_canvas_toolbar_action(
    page: Page,
    action: Literal["zoom_in", "zoom_out", "zoom_100", "fit_view"],
) -> None:
    await flows_e2e_ensure_canvas_layout(page)
    await flows_dismiss_blocking_overlays(page)
    await flows_close_floating_panel(page)
    if action == "fit_view":
        canvas = page.locator("flows-flow-canvas").first
        await expect(canvas).to_be_visible(timeout=5_000)
        await canvas.evaluate(
            """
            (el) => {
                if (typeof el._fitView === 'function') {
                    el._fitView();
                    return;
                }
                throw new Error('flows-flow-canvas._fitView unavailable');
            }
            """
        )
        return
    toolbar = page.locator("flows-bottom-toolbar").first
    await expect(toolbar).to_be_visible(timeout=5_000)
    icon_map = {
        "zoom_in": "plus",
        "zoom_out": "minus",
        "zoom_100": "search",
    }
    icon = icon_map[action]
    btn = (
        toolbar.locator(f"platform-icon[name='{icon}']")
        .locator("xpath=ancestor::platform-button")
        .first
    )
    await expect(btn).to_be_visible(timeout=5_000)
    await btn.evaluate("(el) => el.click()")


# --------------------------------------------------------------------------------------
# Editor overflow menu, modals, observability, chat helpers.
# --------------------------------------------------------------------------------------


async def flows_click_editor_overflow(
    page: Page,
    *label_patterns: str,
    icon: str | None = None,
) -> None:
    """Кликает пункт overflow-меню. Предпочтительно по icon (i18n может показать сырой ключ)."""
    if not label_patterns and not icon:
        raise ValueError("overflow menu requires label_patterns and/or icon.")
    await flows_dismiss_blocking_overlays(page)
    overflow_btn = (
        page.locator(
            "flows-editor-header .overflow-btn-wrap platform-button, "
            "flows-editor-header platform-icon[name='more-vertical']"
        )
        .locator("xpath=ancestor::platform-button")
        .first
    )
    await expect(overflow_btn).to_be_visible(timeout=15_000)
    await overflow_btn.evaluate("(el) => el.click()")
    portal = page.locator(".flows-editor-header-menu-portal:not(.problems-flyout)").first
    await expect(portal).to_be_visible(timeout=10_000)
    item: Locator | None = None
    if icon:
        by_icon = portal.locator(f"platform-button:has(platform-icon[name='{icon}'])").first
        if await by_icon.count() > 0:
            item = by_icon
    if item is None:
        if not label_patterns:
            raise AssertionError(f"overflow menu item not found for icon={icon!r}")
        pattern = re.compile("|".join(re.escape(label) for label in label_patterns))
        item = portal.get_by_role("button", name=pattern).first
        if await item.count() == 0:
            item = portal.locator("platform-button").filter(has_text=pattern).first
    await expect(item).to_be_visible(timeout=10_000)
    await item.scroll_into_view_if_needed()
    await item.evaluate("(el) => el.click()")


async def flows_open_variables_modal(
    page: Page, *, scope: Literal["flow", "company"] = "flow"
) -> Locator:
    """Открывает модалку переменных через openModal — без клика по toolbar (overlay/FAB)."""
    await flows_dismiss_blocking_overlays(page)
    if scope == "flow":
        await flows_close_floating_panel(page)
        opened = await page.evaluate(
            """
            () => {
                const app = document.querySelector('flows-app');
                if (!app || typeof app.openModal !== 'function') {
                    throw new Error('flows-app.openModal is unavailable');
                }
                const path = window.location.pathname;
                const match = path.match(/\\/flows\\/([^/]+)\\/editor(?:\\/([^/]+))?\\/?$/);
                if (!match) {
                    throw new Error(`flowId not found in path: ${path}`);
                }
                app.openModal('flows.variables', { scope: 'flow', flowId: match[1] });
                return match[1];
            }
            """
        )
        if not isinstance(opened, str) or not opened:
            raise AssertionError("flows_open_variables_modal: flowId missing after openModal")
    else:
        await page.goto(page.url.split("/flows/")[0] + "/flows/", wait_until="domcontentloaded")
        home = page.locator("flows-home-page").first
        await expect(home).to_be_visible(timeout=30_000)
        await page.evaluate(
            """
            () => {
                const app = document.querySelector('flows-app');
                if (!app || typeof app.openModal !== 'function') {
                    throw new Error('flows-app.openModal is unavailable');
                }
                app.openModal('flows.variables', { scope: 'company' });
            }
            """
        )
    modal = page.locator("flows-variables-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_add_flow_variable(page: Page, key: str, value: str) -> None:
    modal = page.locator("flows-variables-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    add_btn = (
        modal.locator("platform-button[icon-only], platform-button")
        .filter(has=page.locator("platform-icon[name='plus']"))
        .first
    )
    await expect(add_btn).to_be_visible(timeout=15_000)
    await add_btn.evaluate("(el) => el.click()")
    var_editor = page.locator("flows-variable-editor-modal").first
    await expect(var_editor).to_be_visible(timeout=15_000)
    fields = var_editor.locator("platform-field")
    await flows_set_platform_field(fields.nth(0), key)
    value_field = fields.filter(has=page.locator("[name='value'], [data-field='value']")).last
    if await value_field.count() == 0:
        value_field = fields.nth(-1)
    await flows_set_platform_field(value_field, value)
    await flows_save_variable_editor_modal(var_editor)


async def flows_open_triggers_modal(page: Page) -> Locator:
    await flows_click_editor_overflow(
        page,
        "Triggers",
        "Триггеры",
        "editor_header.menu_triggers",
        icon="zap",
    )
    modal = page.locator("flows-triggers-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_open_sessions_modal(page: Page, flows_ui: AppUI) -> Locator:
    _ = flows_ui
    await page.evaluate(
        """
        () => {
            const app = document.querySelector('flows-app');
            if (!app || typeof app.openModal !== 'function') {
                throw new Error('flows-app.openModal is unavailable');
            }
            app.openModal('flows.sessions', {});
        }
        """
    )
    modal = page.locator("flows-sessions-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_open_preview_share_modal(page: Page) -> Locator:
    await flows_click_editor_overflow(
        page,
        "Guest preview link",
        "Share",
        "Поделиться",
        "Preview",
        "editor_header.menu_share",
        icon="share",
    )
    modal = page.locator("flows-preview-share-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_open_integrations_modal_from_home(page: Page, flows_ui: AppUI) -> Locator:
    await page.add_init_script("() => localStorage.setItem('pwa-banner-dismissed', 'true')")
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    home = page.locator("flows-home-page").first
    await expect(home).to_be_visible(timeout=30_000)
    await flows_dismiss_pwa_install_banner(page)
    card = (
        home.locator(".connect-card").filter(has_text=re.compile(r"Integrations|Интеграции")).first
    )
    await expect(card).to_be_visible(timeout=15_000)
    await card.locator("platform-button").first.click()
    modal = page.locator("flows-integrations-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_toggle_breakpoint(page: Page, node_id: str) -> None:
    canvas = page.locator("flows-flow-canvas").first
    await canvas.evaluate(
        """
        (el, nodeId) => {
            if (!el || !el._editor || typeof el._editor.toggleBreakpoint !== 'function') {
                throw new Error('toggleBreakpoint unavailable on flows-flow-canvas');
            }
            el._editor.toggleBreakpoint({ nodeId });
        }
        """,
        node_id,
    )


async def flows_wait_breakpoint_hit(page: Page, node_id: str) -> None:
    hit = page.locator(
        f"flows-flow-canvas g.node[data-node-id='{node_id}'][data-state='breakpoint-hit']"
    ).first
    await expect(hit).to_be_visible(timeout=120_000)


async def flows_continue_breakpoint(page: Page) -> None:
    btn = page.locator(
        "platform-flow-ui .breakpoint-actions button, flows-execution-panel .breakpoint-actions button"
    ).first
    if await btn.count() > 0:
        await btn.click()
        return
    panel = page.locator("flows-execution-panel platform-flow-ui").first
    chat = panel if await panel.count() > 0 else page.locator("platform-flow-ui").first
    continue_btn = chat.locator("button").filter(has_text=re.compile(r"Continue|Продолжить")).first
    await expect(continue_btn).to_be_visible(timeout=15_000)
    await continue_btn.click()


async def flows_open_tracing_from_chat(page: Page) -> Locator:
    btn = page.locator("platform-flow-ui .bubble-observability-actions .tracing-btn").first
    await expect(btn).to_be_visible(timeout=30_000)
    await btn.click()
    modal = page.locator("flows-tracing-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(modal.locator("platform-trace-viewer, .tracing-empty").first).to_be_visible(
        timeout=5_000
    )
    return modal


async def flows_open_logs_from_chat(page: Page) -> Locator:
    btn = page.locator("platform-flow-ui .bubble-observability-actions .tracing-btn").nth(1)
    await expect(btn).to_be_visible(timeout=30_000)
    await btn.click()
    modal = page.locator("flows-logs-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(modal.locator("platform-log-viewer").first).to_be_visible(timeout=5_000)
    return modal


async def flows_open_durable_history_modal(page: Page) -> Locator:
    """Открывает историю выполнения через openModal (без overflow/menu кликов)."""
    await flows_dismiss_blocking_overlays(page)
    chat = page.locator("chat-page").first
    await expect(chat).to_be_visible(timeout=5_000)
    opened = await chat.evaluate(
        """
        (el) => {
            if (typeof el._sessionId !== 'function' || typeof el._openHistory !== 'function') {
                throw new Error('chat-page history API is unavailable');
            }
            const sessionId = el._sessionId();
            if (!sessionId) {
                throw new Error('chat-page has no active session for durable history');
            }
            el._openHistory();
            return sessionId;
        }
        """
    )
    if not isinstance(opened, str) or not opened:
        raise AssertionError("flows_open_durable_history_modal: sessionId missing after openModal")
    modal = page.locator("flows-durable-history-modal").first
    await expect(modal).to_be_visible(timeout=5_000)
    return modal


async def flows_chat_wait_reply(page: Page, text_pattern: str) -> None:
    reply = page.get_by_text(re.compile(text_pattern)).first
    await expect(reply).to_be_visible(timeout=120_000)


async def flows_open_evaluation_from_editor(page: Page, flows_ui: AppUI, flow_id: str) -> None:
    """Открывает Evaluation Lab прямым URL (без overflow-меню — i18n/overlay)."""
    await page.goto(
        f"{flows_ui.origin}/flows/{flow_id}/evaluation/default",
        wait_until="domcontentloaded",
    )
    await flows_dismiss_blocking_overlays(page)
    await expect(page.locator("flows-evaluation-page")).to_be_visible(timeout=15_000)


async def flows_open_branch_create_modal(page: Page) -> Locator:
    await flows_dismiss_blocking_overlays(page)
    await flows_close_floating_panel(page)
    opened = await page.evaluate(
        """
        () => {
            const app = document.querySelector('flows-app');
            if (!app || typeof app.openModal !== 'function') {
                throw new Error('flows-app.openModal is unavailable');
            }
            const path = window.location.pathname;
            const match = path.match(/\\/flows\\/([^/]+)\\/editor/);
            if (!match) {
                throw new Error(`flowId not found in path: ${path}`);
            }
            app.openModal('flows.branch_create', { flowId: match[1] });
            return match[1];
        }
        """
    )
    if not isinstance(opened, str) or not opened:
        raise AssertionError("flows_open_branch_create_modal: flowId missing after openModal")
    modal = page.locator("flows-branch-create-modal").first
    await expect(modal).to_be_visible(timeout=5_000)
    return modal


async def flows_create_branch(
    page: Page,
    branch_id: str,
    name: str,
    *,
    description: str = "",
) -> None:
    modal = await flows_open_branch_create_modal(page)
    await modal.evaluate(
        """
        (el, payload) => {
            el._branchId = payload.branchId;
            el._name = payload.name;
            el._description = payload.description;
            el.isDirty = true;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
        }
        """,
        {"branchId": branch_id, "name": name, "description": description},
    )
    create_btn = (
        modal.locator("platform-button").filter(has_text=re.compile(r"Create|Создать")).first
    )
    await expect(create_btn.locator("button")).to_be_enabled(timeout=15_000)
    async with page.expect_response(
        lambda response: response.request.method == "POST" and "/branches" in response.url,
        timeout=60_000,
    ) as branch_response:
        await create_btn.evaluate("(el) => el.click()")
    response = await branch_response.value
    if response.status >= 400:
        raise AssertionError(
            f"flows_create_branch: POST failed with {response.status}: {await response.text()}"
        )
    await expect(modal).to_be_hidden(timeout=30_000)
    control = page.locator(
        "flows-editor-header .branches-scroll platform-segmented-control, "
        "flows-editor-header .branches-row platform-segmented-control"
    ).first
    await expect(
        control.locator("button.segment .segment-label").filter(
            has_text=re.compile(re.escape(name))
        )
    ).to_be_visible(timeout=30_000)


async def flows_select_branch_tab(page: Page, branch_label_pattern: str) -> None:
    control = page.locator(
        "flows-editor-header .branches-scroll platform-segmented-control, "
        "flows-editor-header .branches-row platform-segmented-control"
    ).first
    await expect(control).to_be_visible(timeout=30_000)
    tab = control.locator("button.segment").filter(has_text=re.compile(branch_label_pattern)).first
    await expect(tab).to_be_visible(timeout=30_000)
    await tab.click()
    await expect(tab).to_have_attribute("data-active", "true", timeout=15_000)


async def flows_open_flow_edit_modal(page: Page) -> Locator:
    settings_btn = page.locator(
        "flows-editor-header platform-button[data-action='flow-settings']"
    ).first
    if await settings_btn.count() > 0 and await settings_btn.is_visible():
        await settings_btn.evaluate("(el) => el.click()")
    else:
        await flows_click_editor_overflow(
            page,
            "Agent settings",
            "Настройки агента",
            "Flow settings",
        )
    modal = page.locator("flows-flow-edit-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_open_flow_property_panel(page: Page) -> Locator:
    panel = page.locator("flows-flow-property-panel").first
    if not await panel.is_visible():
        focus_toggle = page.get_by_role(
            "button",
            name=re.compile(r"Open flow limits and speech settings|Открыть.*лимит|реч", re.I),
        ).first
        if await focus_toggle.count() > 0 and await focus_toggle.is_visible():
            # A node/property overlay can geometrically cover the sidebar after
            # a preceding branch action. This is still the real user control;
            # dispatch its native click without Playwright retrying for 30s.
            await focus_toggle.evaluate("(el) => el.click()")
        else:
            await flows_e2e_ensure_canvas_layout(page)
            toggle = (
                page.locator("flows-node-types-sidebar .trigger-row")
                .filter(has_text=re.compile(r"Limits and speech|Лимиты и речь"))
                .first
            )
            await expect(toggle).to_be_visible(timeout=5_000)
            await toggle.evaluate("(el) => el.click()")
    await expect(panel).to_be_visible(timeout=5_000)
    return panel


async def flows_open_raw_json_modal(page: Page) -> Locator:
    await flows_click_editor_overflow(
        page,
        "Flow JSON",
        "JSON flow",
        "Код",
        "Code",
        "editor_header.menu_code",
        icon="code",
    )
    modal = (
        page.locator("flows-raw-json-modal, platform-modal")
        .filter(has=page.locator("flows-code-editor"))
        .first
    )
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_click_llm_output_mode(
    page: Page,
    mode: Literal["tools", "structured"],
    *,
    node_id: str = "agent",
) -> None:
    await flows_dismiss_blocking_overlays(page)
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor"
    ).first
    # После screenshot/step floating-панель может закрыться — открываем снова.
    if await editor.count() == 0 or not await editor.is_visible():
        await flows_open_node_editor(page, node_id)
        editor = page.locator(
            "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
            "flows-agent-focus-studio flows-llm-node-editor, "
            "flows-property-panel flows-llm-node-editor"
        ).first
    await expect(editor).to_be_visible(timeout=30_000)
    tools_pattern = re.compile(r"Tools|Инструменты", re.I)
    structured_pattern = re.compile(r"Structured|Структурирован", re.I)
    if mode == "tools":
        mode_pattern = tools_pattern
        ready_probe = editor.get_by_role(
            "button",
            name=re.compile(r"From library|Из библиотеки|Add skill|Добавить skill", re.I),
        ).first
    else:
        mode_pattern = structured_pattern
        ready_probe = editor.locator("platform-json-editor").first
    output_mode_control = editor.locator(
        "platform-segmented-control[aria-label='LLM output mode'], "
        "platform-segmented-control[aria-label='Режим вывода LLM']"
    ).first
    await expect(output_mode_control).to_be_visible(timeout=15_000)
    segment = output_mode_control.locator("button.segment").filter(has_text=mode_pattern).first
    await segment.scroll_into_view_if_needed()
    pressed = await segment.get_attribute("aria-pressed")
    if pressed != "true":
        await output_mode_control.evaluate(
            """
            (el, selectedMode) => {
                el.value = selectedMode;
                el.dispatchEvent(
                    new CustomEvent('change', {
                        detail: { value: selectedMode },
                        bubbles: true,
                        composed: true,
                    })
                );
            }
            """,
            mode,
        )
    await expect(segment).to_have_attribute("aria-pressed", "true", timeout=15_000)
    await expect(ready_probe).to_be_visible(timeout=15_000)


async def flows_llm_add_tool_from_library(page: Page, query: str = "") -> None:
    studio = page.locator("flows-agent-focus-studio").first
    if await studio.count() > 0 and await studio.is_visible():
        await flows_e2e_open_studio_skills_tools(page)
    llm_editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor"
    ).first
    await expect(llm_editor).to_be_visible(timeout=5_000)
    await flows_click_platform_button(llm_editor, "Из библиотеки", "From library")
    await flows_pick_first_library_card(page, value=query)


async def flows_library_picker_search(page: Page, query: str) -> None:
    """Ставит поиск в library picker и дожидается server reload (debounce + tools/all?q=)."""
    picker = page.locator("flows-library-picker-modal").first
    await expect(picker).to_be_visible(timeout=30_000)
    search = picker.locator("platform-modal-search-field").first
    await expect(search).to_be_visible(timeout=10_000)
    await picker.evaluate(
        """
        async (el, value) => {
            el._search = value;
            if (el._searchDebounceTimer !== null) {
                clearTimeout(el._searchDebounceTimer);
                el._searchDebounceTimer = null;
            }
            if (typeof el._resetPickerCache === 'function') {
                el._resetPickerCache();
            } else {
                el._pickerItemsByCategory = new Map();
                el._pickerNextOffsetByCategory = new Map();
                el._pickerHasMoreByCategory = new Map();
                el._pickerErrorByCategory = new Map();
                el._pickerLoadingCategory = null;
                el._pickerLoadingMore = false;
                el._pickerActiveQuery = '';
                el._pickerLoadGeneration = (el._pickerLoadGeneration || 0) + 1;
            }
            el._search = value;
            el._pickerActiveQuery = typeof value === 'string' ? value.trim() : '';
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            const category = el._currentPickerCategory();
            await el._ensurePickerCategoryLoaded(category);
            const field = el.renderRoot && el.renderRoot.querySelector
                ? el.renderRoot.querySelector('platform-modal-search-field')
                : null;
            if (field) {
                field.value = value;
                if (typeof field.requestUpdate === 'function') field.requestUpdate();
            }
        }
        """,
        query,
    )
    deadline = time.monotonic() + 20.0
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_state = await picker.evaluate(
            """
            (el, wanted) => ({
                search: el._search,
                loading: el._pickerLoadingCategory,
                ids: el._toolsAllItems().map((x) => x.tool_id),
            })
            """,
            query,
        )
        if (
            isinstance(last_state, dict)
            and last_state.get("search") == query
            and last_state.get("loading") in (None, "")
            and isinstance(last_state.get("ids"), list)
            and wanted_in_ids(last_state["ids"], query)
        ):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"flows library search did not load {query!r}; state={last_state!r}")


def wanted_in_ids(ids: list[Any], query: str) -> bool:
    needle = query.strip().lower()
    if needle == "":
        return True
    for item in ids:
        if isinstance(item, str) and needle in item.lower():
            return True
    return False


async def flows_pick_first_library_card(page: Page, *, value: str = "") -> None:
    picker = page.locator("flows-library-picker-modal").first
    await expect(picker).to_be_visible(timeout=5_000)
    if value:
        await flows_library_picker_search(page, value)
        deadline = time.monotonic() + 15.0
        picked_state: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            picked_state = await picker.evaluate(
                "(el, wanted) => ({ item: el._toolsAllItems().find((x) => x.tool_id === wanted) ?? null, "
                "category: el._currentPickerCategory(), ids: el._toolsAllItems().map((x) => x.tool_id) })",
                value,
            )
            if isinstance(picked_state, dict) and isinstance(picked_state.get("item"), dict):
                break
            await asyncio.sleep(0.05)
        picked = picked_state.get("item") if isinstance(picked_state, dict) else None
        if not isinstance(picked, dict):
            raise AssertionError(f"flows library item not loaded: {value}; state={picked_state!r}")
        if picked.get("item_type") == "flow" and not isinstance(
            picked.get("parameters_schema"), dict
        ):
            raise AssertionError(f"flows library flow has no parameters_schema: {picked!r}")
        # Программный pick: клик по tag-row под xdist/portal часто флакует.
        picked_ok = await picker.evaluate(
            """
            (el, toolId) => {
                const item = el._toolsAllItems().find((x) => x && x.tool_id === toolId);
                if (!item) return false;
                if (typeof el._pickToolLike !== 'function') {
                    throw new Error('flows-library-picker-modal: _pickToolLike missing');
                }
                el._pickToolLike(item);
                return true;
            }
            """,
            value,
        )
        if picked_ok is not True:
            raise AssertionError(f"flows library programmatic pick failed: {value}")
        await expect(picker).to_be_hidden(timeout=15_000)
        return
    row = picker.locator("platform-picker-card").first
    await expect(row).to_be_visible(timeout=15_000)
    await flows_library_picker_activate_row(page, row)


async def flows_library_picker_activate_row(page: Page, row: Locator) -> None:
    """Клик по строке/карточке: в batch-режиме — кнопка «добавить один», иначе сама строка."""
    picker = page.locator("flows-library-picker-modal").first
    add_one = row.locator(
        "platform-button.tag-tool-add-one, "
        'platform-button[aria-label*="Add only"], '
        'platform-button[aria-label*="Добавить только"], '
        'platform-button[title*="Add only"], '
        'platform-button[title*="Добавить только"]'
    ).first
    if await add_one.count() > 0 and await add_one.is_visible():
        target = add_one.locator("button").first
        if await target.count() == 0:
            target = add_one
        await target.click(force=True)
    else:
        card_button = row.locator("article.picker-card").first
        if await card_button.count() > 0:
            await card_button.click(force=True)
        else:
            await row.click(force=True)
    await expect(picker).to_be_hidden(timeout=15_000)


async def flows_library_picker_select_tool(page: Page, *, tool_id: str) -> None:
    picker = page.locator("flows-library-picker-modal").first
    await expect(picker).to_be_visible(timeout=30_000)
    by_data = picker.locator(f'platform-picker-card[data-tool-id="{tool_id}"]').first
    by_card = picker.locator(f'platform-picker-card[value="{tool_id}"]').first
    deadline = time.monotonic() + 30.0
    row: Locator | None = None
    while time.monotonic() < deadline:
        if await by_data.count() > 0 and await by_data.is_visible():
            row = by_data
            break
        if await by_card.count() > 0 and await by_card.is_visible():
            row = by_card
            break
        await asyncio.sleep(0.05)
    if row is None:
        row = (
            picker.locator("platform-picker-card")
            .filter(has_text=re.compile(rf"(?:^|\b){re.escape(tool_id)}(?:\b|$)", re.I))
            .first
        )
        await expect(row).to_be_visible(timeout=5_000)
    await flows_library_picker_activate_row(page, row)


async def flows_pick_library_card_by_text(page: Page, text: str) -> None:
    await flows_library_picker_search(page, text)
    await flows_library_picker_select_tool(page, tool_id=text)


async def flows_drop_resource_type(
    page: Page,
    resource_type: str,
    *,
    x: int = 480,
    y: int = 520,
    name: str | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Добавляет resource-ноду в branchData (без DnD). Возвращает node_id."""
    await flows_e2e_ensure_canvas_layout(page)
    await flows_dismiss_blocking_overlays(page)
    canvas = page.locator("flows-flow-canvas").first
    await expect(canvas).to_be_visible(timeout=5_000)
    # Дождаться load flow — иначе inject перетирается поздним branch_data.
    deadline_ready = time.monotonic() + 5.0
    while time.monotonic() < deadline_ready:
        ready = await canvas.evaluate(
            """
            (el) => {
                if (!el || typeof el._branchData !== 'function') return false;
                const data = el._branchData();
                const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
                return Object.keys(nodes).length > 0;
            }
            """
        )
        if ready is True:
            break
        await asyncio.sleep(0.1)
    else:
        raise AssertionError("flows_drop_resource_type: branchData empty after wait")

    resource_name = name if name is not None else resource_type
    resource_config = config if config is not None else {}
    inject_js = """
        (el, ctx) => {
            if (!el || !el._editor || typeof el._branchData !== 'function') {
                throw new Error('flows-flow-canvas editor state is unavailable');
            }
            if (typeof el._applyPaletteDrop === 'function') {
                el._applyPaletteDrop({
                    nodeType: '',
                    resourceType: ctx.resourceType,
                    local: { x: ctx.x, y: ctx.y },
                    htmlTargetNodeId: null,
                });
                const data = el._branchData();
                const nodes = data && data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
                const resourceNodes = Object.entries(nodes)
                    .filter(([, node]) => node && node.type === 'resource')
                    .map(([id]) => id);
                if (resourceNodes.length === 0) {
                    throw new Error('flows_drop_resource_type: _applyPaletteDrop created no resource node');
                }
                const nodeId = resourceNodes[resourceNodes.length - 1];
                const resources = data.resources && typeof data.resources === 'object' ? data.resources : {};
                const node = nodes[nodeId];
                const bound = node && node.resources && typeof node.resources === 'object'
                    ? Object.keys(node.resources)
                    : [];
                if (bound.length > 0) {
                    const rid = bound[0];
                    const prev = resources[rid] && typeof resources[rid] === 'object' ? resources[rid] : {};
                    const nextResources = {
                        ...resources,
                        [rid]: {
                            ...prev,
                            type: ctx.resourceType,
                            name: ctx.resourceName,
                            config: ctx.resourceConfig,
                        },
                    };
                    const next = { ...data, resources: nextResources };
                    el._editor.updateBranchData({ data: next });
                    el._editor.setDirty({ dirty: true });
                }
                el._editor.selectNode({ nodeId });
                return nodeId;
            }
            throw new Error('flows-flow-canvas._applyPaletteDrop unavailable');
        }
    """
    inject_ctx = {
        "x": x,
        "y": y,
        "resourceType": resource_type,
        "resourceName": resource_name,
        "resourceConfig": resource_config,
    }
    # Повтор при race: поздний branch_data load может перетереть inject.
    last_node_id = ""
    for _attempt in range(3):
        node_id = await canvas.evaluate(inject_js, inject_ctx)
        if not isinstance(node_id, str) or not node_id:
            await asyncio.sleep(0.15)
            continue
        last_node_id = node_id
        present_deadline = time.monotonic() + 2.0
        while time.monotonic() < present_deadline:
            present = await canvas.evaluate(
                """
                (el, selectedNodeId) => {
                    const data = el._branchData();
                    return Boolean(data && data.nodes && data.nodes[selectedNodeId]);
                }
                """,
                node_id,
            )
            if present is True:
                # Короткий settle: убедиться, что late load не стёр ноду.
                await asyncio.sleep(0.35)
                still = await canvas.evaluate(
                    """
                    (el, selectedNodeId) => {
                        const data = el._branchData();
                        return Boolean(data && data.nodes && data.nodes[selectedNodeId]);
                    }
                    """,
                    node_id,
                )
                if still is True:
                    return node_id
                break
            await asyncio.sleep(0.1)
    raise AssertionError(
        f"flows_drop_resource_type: inject not sticky in branchData (last={last_node_id!r})"
    )


async def flows_triggers_click_create(page: Page) -> Locator:
    modal = page.locator("flows-triggers-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    create_btn = modal.locator(
        'platform-button[aria-label*="Создать"], platform-button[aria-label*="Create"]'
    ).first
    await expect(create_btn).to_be_visible(timeout=15_000)
    await create_btn.locator("button").first.click()
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    return editor


async def flows_trigger_editor_select_type(page: Page, trigger_type: str) -> None:
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    option = editor.locator(".trigger-type-option").filter(has=page.locator("platform-icon"))
    type_labels = {
        "telegram": re.compile(r"Telegram"),
        "cron": re.compile(r"Cron|Расписан"),
        "webhook": re.compile(r"Webhook"),
        "email": re.compile(r"Почта|Email|Mail", re.I),
        "platform_event": re.compile(r"Событие платформы|Platform event", re.I),
    }
    label = type_labels.get(trigger_type)
    if label is None:
        raise ValueError(f"Unsupported trigger type for UI picker: {trigger_type!r}")
    target = option.filter(has_text=label).first
    await expect(target).to_be_visible(timeout=15_000)
    await target.click()


async def flows_trigger_editor_expect_sample_panel(page: Page) -> None:
    """Mapping tab: sample payload panel visible."""
    editor = page.locator("flows-trigger-editor-modal").first
    await flows_trigger_editor_open_tab(page, "mapping")
    await expect(editor.locator(".sample-payload-block").first).to_be_visible(timeout=15_000)
    await expect(editor.locator("pre.sample-json").first).to_be_visible(timeout=10_000)


async def flows_trigger_editor_expect_ready_curl(page: Page) -> None:
    """Config tab: ready curl block for webhook/telegram."""
    editor = page.locator("flows-trigger-editor-modal").first
    await flows_trigger_editor_open_tab(page, "config")
    curl_box = editor.locator("pre.curl-box").first
    await expect(curl_box).to_be_visible(timeout=15_000)
    curl_text = await curl_box.inner_text()
    if "curl -X POST" not in curl_text:
        raise AssertionError(f"ready curl missing POST: {curl_text!r}")


async def flows_trigger_editor_fill_identity(
    page: Page,
    *,
    trigger_id: str,
    name: str,
) -> None:
    editor = page.locator("flows-trigger-editor-modal").first
    fields = editor.locator("platform-field")
    await flows_set_platform_field(fields.nth(1), trigger_id)
    await flows_set_platform_field(fields.nth(2), name)


async def flows_trigger_editor_configure_webhook(
    page: Page,
    *,
    secret_token: str,
    secret_header: str = "X-Trigger-Secret",
    allowed_ips: list[str] | None = None,
) -> None:
    """Заполняет webhook config (secret / header / IP tags) на вкладке Configuration."""
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    ips = list(allowed_ips) if allowed_ips is not None else ["127.0.0.1"]
    await editor.evaluate(
        """
        (el, payload) => {
            el._config = {
                ...(el._config && typeof el._config === 'object' ? el._config : {}),
                secret_token: payload.secret_token,
                secret_header: payload.secret_header,
                allowed_ips: payload.allowed_ips,
            };
            el.isDirty = true;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
        }
        """,
        {
            "secret_token": secret_token,
            "secret_header": secret_header,
            "allowed_ips": ips,
        },
    )
    await expect(editor.locator(".config-intro").first).to_be_visible(timeout=10_000)


async def flows_trigger_editor_configure_platform_event(
    page: Page,
    *,
    event_type: str,
    filters: list[dict[str, object]] | None = None,
) -> None:
    """Задаёт event_type + filters на вкладке Configuration (реальный catalog на бэке)."""
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    await expect(
        editor.locator(".config-section-title").filter(
            has_text=re.compile(r"Событие платформы|Platform event", re.I)
        )
    ).to_be_visible(timeout=15_000)
    # Catalog async load — ждём enum event_type
    await expect(editor.locator("platform-field[type='enum']").first).to_be_visible(timeout=30_000)
    filter_rows = list(filters) if filters is not None else []
    await editor.evaluate(
        """
        (el, payload) => {
            el._config = {
                ...(el._config && typeof el._config === 'object' ? el._config : {}),
                event_type: payload.event_type,
                filters: payload.filters,
            };
            el._outputMapping = [
                { state: 'content', payload: '@const:platform_event' },
            ];
            el.isDirty = true;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
        }
        """,
        {"event_type": event_type, "filters": filter_rows},
    )
    await expect(editor.locator(".event-filter-row")).to_have_count(
        len(filter_rows), timeout=10_000
    )


async def flows_trigger_editor_platform_event_change_type_clears_filters(
    page: Page,
    *,
    next_event_type: str,
) -> None:
    """Смена event_type через change → filters сбрасываются в []."""
    editor = page.locator("flows-trigger-editor-modal").first
    event_field = editor.locator(".config-section platform-field[type='enum']").first
    await expect(event_field).to_be_visible(timeout=10_000)
    await event_field.evaluate(
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(
                new CustomEvent('change', {
                    detail: { value },
                    bubbles: true,
                    composed: true,
                })
            );
        }
        """,
        next_event_type,
    )
    cleared = await editor.evaluate(
        """
        (el) => {
            const filters = el._config && Array.isArray(el._config.filters)
                ? el._config.filters
                : null;
            return {
                event_type: el._config ? el._config.event_type : null,
                filters,
            };
        }
        """
    )
    assert cleared["event_type"] == next_event_type
    assert cleared["filters"] == []


async def flows_trigger_editor_open_tab(page: Page, tab: str) -> None:
    editor = page.locator("flows-trigger-editor-modal").first
    control = editor.locator("platform-segmented-control").first
    await expect(control).to_be_visible(timeout=10_000)
    labels = {
        "config": re.compile(r"Configuration|Конфигурац", re.I),
        "mapping": re.compile(r"Mapping|Маппинг", re.I),
        "output": re.compile(r"Output|Вывод", re.I),
    }
    label = labels.get(tab)
    if label is None:
        raise ValueError(f"Unsupported trigger editor tab: {tab!r}")
    button = control.get_by_role("button", name=label).first
    if await button.count() == 0:
        button = control.locator("button, [role='button'], .segment").filter(has_text=label).first
    await expect(button).to_be_visible(timeout=10_000)
    await button.click()


async def flows_trigger_editor_click_mapping_example(page: Page, *, index: int = 0) -> None:
    """Кликает пример маппинга — должна появиться строка state→payload."""
    editor = page.locator("flows-trigger-editor-modal").first
    await flows_trigger_editor_open_tab(page, "mapping")
    example = editor.locator("article.examples-row, button.examples-row").nth(index)
    await expect(example).to_be_visible(timeout=10_000)
    before = await editor.locator(".mapping-row").count()
    await example.click()
    await expect(editor.locator(".mapping-row")).to_have_count(before + 1, timeout=10_000)


async def flows_save_variable_editor_modal(modal: Locator) -> None:
    await flows_click_platform_button(
        modal, "Сохранить", "Save", "Готово", "Done", "Создать", "Create"
    )


async def flows_trigger_editor_save(page: Page) -> None:
    editor = page.locator("flows-trigger-editor-modal").first
    await flows_click_platform_button(
        editor,
        "Создать",
        "Create",
        "Сохранить",
        "Save",
    )
    await expect(editor).to_be_hidden(timeout=30_000)


async def flows_trigger_editor_configure_cron(
    page: Page,
    *,
    cron: str,
    timezone: str,
    initial_content: str,
) -> None:
    """Заполняет cron / timezone / initial_content на вкладке Configuration."""
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    await editor.evaluate(
        """
        (el, payload) => {
            el._config = {
                ...(el._config && typeof el._config === 'object' ? el._config : {}),
                cron: payload.cron,
                timezone: payload.timezone,
                initial_content: payload.initial_content,
            };
            el.isDirty = true;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
        }
        """,
        {
            "cron": cron,
            "timezone": timezone,
            "initial_content": initial_content,
        },
    )
    cron_field = editor.locator("platform-cron-field").first
    await expect(cron_field).to_be_visible(timeout=10_000)
    await expect(editor.locator("platform-timezone-picker").first).to_be_visible(timeout=10_000)


async def flows_trigger_editor_configure_telegram(
    page: Page,
    *,
    bot_token: str,
    allowed_users: list[int] | None = None,
) -> None:
    """Токен бота и опциональный список Telegram user_id."""
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    users = list(allowed_users) if allowed_users is not None else []
    await editor.evaluate(
        """
        (el, payload) => {
            el._config = {
                ...(el._config && typeof el._config === 'object' ? el._config : {}),
                bot_token: payload.bot_token,
                allowed_users: payload.allowed_users,
            };
            el.isDirty = true;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
        }
        """,
        {"bot_token": bot_token, "allowed_users": users},
    )
    await expect(
        editor.locator(".config-section-title").filter(has_text=re.compile(r"Telegram", re.I))
    ).to_be_visible(timeout=10_000)


async def flows_trigger_editor_click_email_mailbox(
    page: Page,
    *,
    email_address: str,
) -> None:
    editor = page.locator("flows-trigger-editor-modal").first
    chip = (
        editor.locator("article.email-chip, button.email-chip").filter(has_text=email_address).first
    )
    await expect(chip).to_be_visible(timeout=20_000)
    await chip.click()
    await expect(chip).to_have_class(re.compile(r"\bactive\b"), timeout=10_000)


async def flows_trigger_editor_apply_email_filter_preset(
    page: Page,
    *,
    preset_label: re.Pattern[str] | str,
) -> None:
    editor = page.locator("flows-trigger-editor-modal").first
    label = (
        preset_label
        if isinstance(preset_label, re.Pattern)
        else re.compile(re.escape(preset_label), re.I)
    )
    chip = (
        editor.locator(
            ".email-preset-list article.email-chip, .email-preset-list button.email-chip"
        )
        .filter(has_text=label)
        .first
    )
    await expect(chip).to_be_visible(timeout=15_000)
    await chip.click()
    await expect(chip).to_have_class(re.compile(r"\bactive\b"), timeout=10_000)


async def flows_seed_ui_mail_mailbox(
    frontend_di: Any,
    *,
    unique_id: str,
    local_part: str | None = None,
) -> MailboxBinding:
    """Создаёт ACTIVE company mail + USER mailbox для primary UI E2E company."""
    from core.context import clear_context, set_context
    from core.mail.models import (
        CompanyMailConnectionUpsertPayload,
        MailboxBinding,
        MailboxBindingCreatePayload,
        MailboxBindingKind,
        MailProvider,
    )
    from core.mail.service import MailService
    from core.models.context_models import Context
    from core.models.identity_models import Company, User
    from tests.core.mail.fakes import RecordingMailServerPort
    from tests.ui.e2e_worker import ui_e2e_company_id, ui_e2e_worker_id

    company_id = ui_e2e_company_id()
    user_id = f"ui_owner_{ui_e2e_worker_id()}"
    company = await Company.get(company_id)
    user = await User.get(user_id)
    if company is None or user is None:
        raise RuntimeError(
            f"UI E2E company/user missing for mail seed: {company_id!r} / {user_id!r}"
        )
    if not isinstance(company, Company) or not isinstance(user, User):
        raise TypeError("flows_seed_ui_mail_mailbox: unexpected company/user types")

    port = RecordingMailServerPort(supports_provision=False)
    base_mail = frontend_di.mail_service
    mail_service = MailService(
        authz=base_mail._authz,
        namespace_service=base_mail._namespace_service,
        rag_client=base_mail._rag_client,
        mail_config=base_mail._mail_config,
        port_override=port,
        files_service=base_mail._files_service,
        attachment_file_index=base_mail._attachment_file_index,
        calendar_bridge=base_mail._calendar_bridge,
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="ui_e2e",
        )
    )
    try:
        _ = await mail_service.upsert_connection(
            CompanyMailConnectionUpsertPayload(
                mail_domain=f"ui-mail-{unique_id[:10]}.example.com",
                provider=MailProvider.GENERIC_IMAP_SMTP,
                imap_host="imap.example.com",
                imap_port=993,
                smtp_host="smtp.example.com",
                smtp_port=465,
                use_ssl=True,
            ),
            company_id=company_id,
        )
        part = local_part if local_part is not None else f"orders{unique_id[:6]}"
        binding = await mail_service.bind_mailbox(
            MailboxBindingCreatePayload(
                kind=MailboxBindingKind.USER,
                user_id=user_id,
                local_part=part,
                password="ui-e2e-mail-pass",
                provision=False,
                sync_enabled=True,
            ),
            company_id=company_id,
        )
    finally:
        clear_context()
    if not isinstance(binding, MailboxBinding):
        raise TypeError("flows_seed_ui_mail_mailbox: bind_mailbox must return MailboxBinding")
    return binding


async def flows_set_code_node_source(page: Page, code: str) -> None:
    workbench = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench"
    ).first
    await expect(workbench).to_be_visible(timeout=30_000)
    code_editor = workbench.locator("flows-code-editor").first
    await expect(code_editor).to_be_visible(timeout=30_000)
    await code_editor.evaluate(
        """
        (el, value) => {
            if (el._editorView) {
                el._editorView.dispatch({
                    changes: {
                        from: 0,
                        to: el._editorView.state.doc.length,
                        insert: value,
                    },
                });
                return;
            }
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(
                new CustomEvent('change', {
                    detail: { value },
                    bubbles: true,
                    composed: true,
                })
            );
        }
        """,
        code,
    )


async def flows_code_editor_content(page: Page) -> Locator:
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    await expect(editor).to_be_visible(timeout=30_000)
    content = editor.locator(".cm-content")
    await expect(content).to_be_visible(timeout=30_000)
    return content


async def flows_code_caret_after(page: Page, needle: str) -> None:
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    await expect(editor).to_be_visible(timeout=30_000)
    placed_raw: object = await editor.evaluate(
        """
        (el, needle) => {
            if (!el._editorView) {
                throw new Error('codemirror is not mounted');
            }
            const doc = el._editorView.state.doc.toString();
            const index = doc.lastIndexOf(needle);
            if (index < 0) {
                throw new Error(`code editor needle ${JSON.stringify(needle)} is missing`);
            }
            const pos = index + needle.length;
            el._editorView.dispatch({ selection: { anchor: pos, head: pos } });
            el._editorView.focus();
            return true;
        }
        """,
        needle,
    )
    if placed_raw is not True:
        raise AssertionError(f"code editor caret was not placed after {needle!r}")


async def flows_e2e_visible_loaders(page: Page) -> list[str]:
    raw = await page.evaluate(
        """
        (selector) => {
            const matches = [];
            const walk = (root) => {
                if (!root || !root.querySelectorAll) return;
                for (const el of root.querySelectorAll(selector)) matches.push(el);
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) walk(el.shadowRoot);
                }
            };
            const isPainted = """
        + ELEMENT_IS_PAINTED_JS
        + """;
            walk(document);
            return matches.filter(isPainted).map((el) => {
                const tag = el.tagName.toLowerCase();
                const id = el.id ? '#' + el.id : '';
                const cls = typeof el.className === 'string' && el.className.trim()
                    ? '.' + el.className.trim().split(/\\s+/).join('.')
                    : '';
                const root = el.getRootNode();
                const host = root && root.host ? root.host.tagName.toLowerCase() : '';
                return (host ? host + ' / ' : '') + tag + id + cls;
            });
        }
        """,
        LOADING_SELECTOR,
    )
    if not isinstance(raw, list):
        raise AssertionError(f"visible loaders payload must be a list, got {raw!r}")
    return [str(item) for item in raw if isinstance(item, str) and item]


async def flows_e2e_wait_no_blocking_loaders(page: Page, *, timeout_ms: int = 30_000) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last: list[str] = []
    while time.monotonic() < deadline:
        last = await flows_e2e_visible_loaders(page)
        if last == []:
            return
        await page.wait_for_timeout(200)
    raise AssertionError(f"blocking loaders still visible: {last!r}")


async def flows_code_editor_focus(page: Page) -> Locator:
    content = await flows_code_editor_content(page)
    await content.click()
    return content


async def flows_code_editor_type(page: Page, text: str) -> None:
    await flows_code_editor_focus(page)
    await page.keyboard.type(text, delay=25)


async def flows_code_wait_editor_mounted(
    page: Page,
    *,
    node_id: str = "echo",
    timeout_ms: int = 90_000,
) -> None:
    """Ждёт CodeMirror в открытой floating-панели; при detach снова открывает ноду."""
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break
        if await editor.count() == 0 or not await editor.is_visible():
            _ = await flows_open_node_editor(page, node_id)
            await page.wait_for_timeout(200)
            continue
        try:
            mounted_raw: object = await editor.evaluate(
                """
                (el) => {
                    if (el._editorView) {
                        return true;
                    }
                    if (typeof el._ensureEditorMounted === 'function') {
                        void el._ensureEditorMounted();
                    }
                    return false;
                }
                """,
                timeout=min(5_000, remaining_ms),
            )
        except PlaywrightTimeoutError:
            _ = await flows_open_node_editor(page, node_id)
            await page.wait_for_timeout(200)
            continue
        if mounted_raw is True:
            return
        await page.wait_for_timeout(200)
    raise AssertionError("code editor CodeMirror is not mounted")


async def flows_code_wait_lsp_ready(
    page: Page,
    *,
    language: str | None = None,
    timeout_ms: int = 90_000,
) -> None:
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    await expect(editor).to_be_visible(timeout=timeout_ms)
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break
        try:
            ready_raw = await editor.evaluate(
                """
                (el, expectedLanguage) => {
                    if (expectedLanguage && el.language !== expectedLanguage) {
                        return false;
                    }
                    return Boolean(
                        !el._lspRestartTimer
                        && el._lspClient
                        && el._lspSocket
                        && el._lspSocket.readyState === 1
                        && el._lspClient.serverCapabilities
                    );
                }
                """,
                language,
                timeout=min(5_000, remaining_ms),
            )
        except PlaywrightTimeoutError:
            await page.wait_for_timeout(200)
            continue
        if ready_raw is True:
            return
        await page.wait_for_timeout(200)
    raise AssertionError(
        f"code editor language server is not initialized (language={language!r})"
    )


async def flows_code_editor_trigger_completion(page: Page) -> None:
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    started_raw: object = await editor.evaluate(
        """
        (el) => {
            if (!el._cm || !el._editorView) {
                throw new Error('codemirror is not mounted');
            }
            if (typeof el._cm.startCompletion !== 'function') {
                throw new Error('codemirror startCompletion is required');
            }
            el._editorView.focus();
            return el._cm.startCompletion(el._editorView) === true;
        }
        """
    )
    if started_raw is not True:
        await page.keyboard.press("Control+Space")


async def flows_code_wait_completion_labels(
    page: Page,
    *expected: str,
    timeout_ms: int = 90_000,
) -> list[str]:
    mount = page.locator("#flows-cm-tooltip-mount .cm-completionLabel")
    deadline = time.monotonic() + (timeout_ms / 1000)
    last: list[str] = []
    last_trigger = 0.0
    while time.monotonic() < deadline:
        if await mount.count() > 0:
            last = [item.strip() for item in await mount.all_inner_texts() if item.strip()]
            if all(any(needle == label or needle in label for label in last) for needle in expected):
                return last
        now = time.monotonic()
        if now - last_trigger >= 2.0:
            await flows_code_editor_trigger_completion(page)
            last_trigger = now
        await page.wait_for_timeout(300)
    raise AssertionError(f"code completion missing {expected!r}; labels={last!r}")


async def flows_code_hover_token(page: Page, token: str, *, timeout_ms: int = 30_000) -> str:
    await page.keyboard.press("Escape")
    autocomplete = page.locator("#flows-cm-tooltip-mount .cm-tooltip-autocomplete")
    await expect(autocomplete).to_have_count(0, timeout=5_000)
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    await expect(editor).to_be_visible(timeout=30_000)
    opened_raw: object = await editor.evaluate(
        """
        async (el, token) => {
            if (!el._editorView || !el._cm || !el._lspClient) {
                throw new Error('code editor language server is not mounted');
            }
            const view = el._editorView;
            const client = el._lspClient;
            const doc = view.state.doc.toString();
            const index = doc.lastIndexOf(token);
            if (index < 0) {
                throw new Error(`code editor token ${JSON.stringify(token)} is missing`);
            }
            const createOffset = token.indexOf('create');
            const pos = createOffset >= 0
                ? index + createOffset + 2
                : index + Math.max(1, Math.floor(token.length / 2));
            const file = client.workspace.files[0];
            if (!file || typeof file.uri !== 'string') {
                throw new Error('code editor workspace file is required');
            }
            client.sync();
            const line = view.state.doc.lineAt(pos);
            const result = await client.request('textDocument/hover', {
                textDocument: { uri: file.uri },
                position: { line: line.number - 1, character: pos - line.from },
            });
            if (!result || result.contents == null) {
                throw new Error('language server hover is empty');
            }
            const asText = (contents) => {
                if (typeof contents === 'string') {
                    return contents;
                }
                if (Array.isArray(contents)) {
                    return contents.map(asText).join('\\n');
                }
                if (contents && typeof contents.value === 'string') {
                    return contents.value;
                }
                throw new Error('language server hover contents are not text');
            };
            const text = asText(result.contents).trim();
            if (!text) {
                throw new Error('language server hover text is empty');
            }
            if (!el._cm.showTooltip || typeof el._cm.showTooltip.of !== 'function' || !el._cm.StateEffect) {
                throw new Error('codemirror showTooltip is required');
            }
            const tooltipPos = result.range
                ? view.state.doc.line(result.range.start.line + 1).from + result.range.start.character
                : pos;
            view.dispatch({
                effects: el._cm.StateEffect.appendConfig.of(
                    el._cm.showTooltip.of({
                        pos: tooltipPos,
                        above: true,
                        create() {
                            const dom = document.createElement('div');
                            dom.className = 'cm-lsp-hover-tooltip cm-lsp-documentation';
                            dom.textContent = text;
                            return { dom };
                        },
                    }),
                ),
            });
            return text;
        }
        """,
        token,
    )
    if not isinstance(opened_raw, str) or opened_raw.strip() == "":
        raise AssertionError(f"hover tooltip empty for {token!r}; payload={opened_raw!r}")
    tooltip = page.locator(".cm-lsp-hover-tooltip, #flows-cm-tooltip-mount .cm-tooltip")
    await expect(tooltip.last).to_be_visible(timeout=timeout_ms)
    shown = (await tooltip.last.inner_text()).strip()
    if shown == "":
        raise AssertionError(f"hover tooltip empty for {token!r}")
    return shown


async def flows_switch_code_language(page: Page, language: str) -> None:
    titles = {
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "go": "Go",
        "csharp": "C#",
    }
    if language not in titles:
        raise ValueError(f"unknown code language {language!r}")
    button = page.locator(
        "flows-floating-panel[show-backdrop] "
        f"flows-code-workbench flows-code-language-segment button.segment[title='{titles[language]}']"
    )
    await expect(button).to_be_visible(timeout=10_000)
    await button.click()


async def flows_code_wait_diagnostic(page: Page, *, timeout_ms: int = 90_000) -> None:
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-code-workbench flows-code-editor"
    ).first
    marker = editor.locator(
        ".cm-lintRange-error, .cm-lintPoint-error, .cm-lintRange.cm-lintRange-error, "
        ".cm-lintRange-warning, .cm-lintRange-unused"
    )
    await expect(marker.first).to_be_visible(timeout=timeout_ms)
    toast = page.locator("glass-toast").filter(
        has_text=re.compile(r"language server|language server редактора", re.I)
    )
    await expect(toast).to_have_count(0)


async def flows_code_assert_no_lsp_failed_toast(page: Page) -> None:
    toast = page.locator("glass-toast").filter(
        has_text=re.compile(
            r"Failed to connect the code editor language server|Не удалось подключить language server",
            re.I,
        )
    )
    await expect(toast).to_have_count(0)


async def flows_ensure_channel_node_telegram(page: Page) -> None:
    editor = page.locator("flows-channel-node-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    channel_field = editor.locator("platform-field[type='enum']").first
    await channel_field.evaluate(
        """
        (el) => {
            el.value = 'telegram';
            el.dispatchEvent(
                new CustomEvent('change', {
                    detail: { value: 'telegram' },
                    bubbles: true,
                    composed: true,
                })
            );
        }
        """
    )


async def flows_set_remote_flow_url(
    page: Page,
    url: str,
    *,
    branch_id: str = "default",
    node_id: str | None = None,
) -> None:
    if node_id is not None:
        await flows_open_node_editor(page, node_id)
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-remote-flow-editor, flows-remote-flow-editor"
    ).first
    await expect(editor).to_be_visible(timeout=10_000)
    await expect(editor.locator("[data-testid='remote-flow-protocol-panel']")).to_be_visible(
        timeout=5_000
    )
    endpoint_fields = editor.locator(".remote-flow-endpoint-stack platform-field")
    url_field = endpoint_fields.first
    await expect(url_field).to_be_visible(timeout=5_000)
    await flows_set_platform_field(url_field, url)
    branch_field = endpoint_fields.nth(1)
    await flows_set_platform_field(branch_field, branch_id)


async def flows_set_external_api_url(page: Page, url: str) -> None:
    editor = page.locator(
        "flows-external-api-editor, flows-floating-panel flows-external-api-editor"
    ).first
    await expect(editor).to_be_visible(timeout=5_000)
    url_field = editor.locator(".settings-wrap platform-field[input-type='url']").first
    await flows_set_platform_field(url_field, url)


async def flows_set_llm_call_type(page: Page, call_type: Literal["call", "handoff"]) -> None:
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor"
    ).first
    await expect(editor).to_be_visible(timeout=30_000)
    mode_button = editor.locator(".chip .chip-call-type").first
    await expect(mode_button).to_be_visible(timeout=30_000)
    current = await mode_button.get_attribute("data-call-type")
    if current != call_type:
        await mode_button.click()
    await expect(mode_button).to_have_attribute("data-call-type", call_type)


def flows_code_echo_payload(flow_id: str, *, name: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "Code echo node for UI scenario",
        "entry": "echo",
        "nodes": {
            "echo": {
                "type": "code",
                "name": "Echo",
                "language": "python",
                "code": (
                    "async def run(args, state):\n"
                    "    content = str(state.get('content', ''))\n"
                    "    state['response'] = 'echo:' + content\n"
                    "    return state\n"
                ),
            },
        },
        "edges": [{"from_node": "echo", "to_node": None}],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_code_echo_with_telegram_channel_payload(
    flow_id: str,
    *,
    name: str,
    bot_token: str,
    channel_node_id: str = "telegram_notify",
) -> dict[str, Any]:
    """Code echo + channel(telegram) на графе (без DnD в UI)."""
    payload = flows_code_echo_payload(flow_id, name=name)
    nodes = payload["nodes"]
    if not isinstance(nodes, dict):
        raise AssertionError("flows_code_echo_payload nodes must be a dict")
    nodes[channel_node_id] = {
        "type": "channel",
        "channel": "telegram",
        "action": "send_message",
        "name": "Telegram",
        "pos_x": 420,
        "pos_y": 300,
        "channel_config": {
            "bot_token": bot_token,
        },
        "input_mapping": {
            "recipient": "@state:chat_id",
            "text": "@state:response",
        },
    }
    edges = payload["edges"]
    if not isinstance(edges, list):
        raise AssertionError("flows_code_echo_payload edges must be a list")
    edges[:] = [
        {"from_node": "echo", "to_node": channel_node_id},
        {"from_node": channel_node_id, "to_node": None},
    ]
    return payload


def flows_external_api_payload(flow_id: str, *, name: str, url: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "Order tracking external API demo",
        "entry": "tracker",
        "nodes": {
            "tracker": {
                "type": "external_api",
                "name": GREEN_GARDEN_ORDER_TRACKER,
                "method": "GET",
                "url": url,
                "headers": {},
                "timeout": 30,
            },
        },
        "edges": [{"from_node": "tracker", "to_node": None}],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_remote_agent_payload(flow_id: str, *, name: str, url: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "Remote A2A agent demo",
        "entry": "remote_partner",
        "nodes": {
            "remote_partner": {
                "type": "remote_flow",
                "name": "Remote partner",
                "url": url,
                "branch_id": "default",
                "headers": {},
                "pos_x": 360,
                "pos_y": 280,
            },
        },
        "edges": [{"from_node": "remote_partner", "to_node": None}],
        "variables": {},
        "tags": ["docs", "scenario"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


def flows_multi_orchestrator_payload(flow_id: str, *, name: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "Orchestrator with sub-agents",
        "entry": "orchestrator",
        "nodes": {
            "orchestrator": {
                "type": "llm_node",
                "name": "Orchestrator",
                "prompt": "Направляй запросы подходящему помощнику магазина.",
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
        "tags": ["docs", "scenario", "preset:multi"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


# --------------------------------------------------------------------------------------
# Agent Skills, Focus Studio layout, Lara, chat settings (docs revision helpers).
# --------------------------------------------------------------------------------------


async def flows_e2e_seed_agent_skill(
    origin: str,
    auth_token: str,
    *,
    agent_skill_id: str,
    name: str,
    description: str,
    body_markdown: str,
    tool_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """HTTP create Agent Skill for UI/E2E scenarios."""
    payload: dict[str, Any] = {
        "agent_skill_id": agent_skill_id,
        "name": name,
        "description": description,
        "body_markdown": body_markdown,
        "tool_refs": tool_refs or [],
        "depends_on": [],
        "references": [],
        "assets": [],
    }
    async with _flows_client(origin, auth_token) as client:
        delete = await client.delete(f"/flows/api/v1/agent-skills/{agent_skill_id}")
        if delete.status_code not in (200, 204, 404):
            delete.raise_for_status()
        response = await client.post("/flows/api/v1/agent-skills", json=payload)
        if response.status_code not in (200, 201):
            raise AssertionError(
                f"create agent skill failed: {response.status_code} {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise AssertionError(f"agent skill response must be object, got {type(body)}")
        return body


async def flows_e2e_set_skill_body(page: Page, body_markdown: str) -> None:
    editor = page.locator("flows-agent-skill-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    code_editor = editor.locator("flows-code-editor").first
    await expect(code_editor).to_be_visible(timeout=15_000)
    await code_editor.evaluate(
        """
        (el, value) => {
            if (el._editorView) {
                el._editorView.dispatch({
                    changes: {
                        from: 0,
                        to: el._editorView.state.doc.length,
                        insert: value,
                    },
                });
            }
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        body_markdown,
    )


async def flows_e2e_save_skill_editor(page: Page) -> None:
    editor = page.locator("flows-agent-skill-editor").first
    await flows_click_platform_button(editor, "Сохранить", "Save")


async def flows_e2e_open_skill_library(page: Page, flows_ui: AppUI) -> None:
    await page.goto(f"{flows_ui.origin}/flows/skills", wait_until="domcontentloaded")
    await expect(page.locator("flows-agent-skills-page")).to_be_visible(timeout=30_000)


async def flows_e2e_set_llm_output_mode(
    page: Page,
    mode: Literal["tools", "structured"],
) -> None:
    await flows_click_llm_output_mode(page, mode)


def _flows_flow_id_from_editor_url(page: Page) -> str:
    path = urlparse(page.url).path
    match = re.search(r"/flows/([^/]+)/editor", path)
    if match is None:
        raise AssertionError(f"flows editor URL without flow_id: {page.url!r}")
    return match.group(1)


async def flows_e2e_switch_editor_layout(
    page: Page,
    layout: Literal["agent", "canvas"],
) -> None:
    """Переключает Agent Focus Studio <-> канва через setEditorLayout (без reload)."""
    if layout not in {"agent", "canvas"}:
        raise ValueError(f"layout must be agent|canvas, got {layout!r}")
    await flows_dismiss_blocking_overlays(page)
    canvas_host = page.locator("flows-flow-canvas svg.canvas-host").first
    studio = page.locator("flows-agent-focus-studio").first
    sidebar = page.locator("flows-node-types-sidebar").first
    if layout == "canvas":
        if (
            await canvas_host.count() > 0
            and await canvas_host.is_visible()
            and await sidebar.count() > 0
            and await sidebar.is_visible()
        ):
            return
    elif await studio.count() > 0 and await studio.is_visible():
        return

    # Studio/page живут в open shadow DOM PlatformApp — только через Playwright locator.
    if layout == "canvas":
        switch_btn = page.get_by_role(
            "button",
            name=re.compile(r"Switch to graph canvas|Переключить на граф", re.I),
        ).first
        if await studio.count() > 0 and await studio.is_visible():
            await studio.evaluate(
                """
                (el) => {
                    if (typeof el._switchToCanvas !== 'function') {
                        throw new Error('flows-agent-focus-studio._switchToCanvas unavailable');
                    }
                    el._switchToCanvas();
                }
                """
            )
        elif await switch_btn.count() > 0 and await switch_btn.is_visible():
            await switch_btn.evaluate("(el) => el.click()")
        else:
            raise AssertionError(
                "flows_e2e_switch_editor_layout(canvas): studio/switch control not found"
            )
        await expect(canvas_host).to_be_visible(timeout=5_000)
        await expect(sidebar).to_be_visible(timeout=5_000)
        return

    editor_page = page.locator("flow-editor-page").first
    await expect(editor_page).to_be_visible(timeout=5_000)
    await editor_page.evaluate(
        """
        (el) => {
            if (typeof el._switchToAgentLayout === 'function') {
                el._switchToAgentLayout();
                return;
            }
            const editor = el._editor;
            if (!editor || typeof editor.setEditorLayout !== 'function') {
                throw new Error('flows/editor.setEditorLayout unavailable');
            }
            const flowId = typeof el.flowId === 'string' ? el.flowId : '';
            if (!flowId) {
                throw new Error('flowId missing on flow-editor-page');
            }
            const segment = flowId
                .toLowerCase()
                .replace(/[^a-z0-9_]+/g, '_')
                .replace(/^_+|_+$/g, '')
                .replace(/_+/g, '_');
            localStorage.setItem(`platform:flows:editor_layout.${segment}`, 'agent');
            editor.setEditorLayout({ layout: 'agent' });
        }
        """
    )
    await expect(studio).to_be_visible(timeout=5_000)


async def flows_e2e_ensure_canvas_layout(page: Page) -> None:
    """Гарантирует канву для helpers, которые кликают g.node / floating panel."""
    canvas_host = page.locator("flows-flow-canvas svg.canvas-host").first
    sidebar = page.locator("flows-node-types-sidebar").first
    if (
        await canvas_host.count() > 0
        and await canvas_host.is_visible()
        and await sidebar.count() > 0
        and await sidebar.is_visible()
    ):
        return
    await flows_e2e_switch_editor_layout(page, "canvas")
    await expect(sidebar).to_be_visible(timeout=5_000)


async def flows_e2e_attach_skill_to_llm_node(page: Page, skill_query: str) -> None:
    editor = page.locator(
        "flows-floating-panel flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor"
    ).first
    await expect(editor).to_be_visible(timeout=30_000)
    await flows_click_platform_button(editor, "Добавить skill", "Add skill")
    picker = page.locator("flows-agent-skill-picker-modal").first
    await expect(picker).to_be_visible(timeout=30_000)
    search = picker.locator("platform-modal-search-field").first
    if await search.count() > 0:
        await search.evaluate(
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
            skill_query,
        )
    card = (
        picker.locator("platform-picker-card")
        .filter(has_text=re.compile(re.escape(skill_query), re.I))
        .first
    )
    await expect(card).to_be_visible(timeout=30_000)
    await card.click(force=True)
    confirm = (
        picker.locator("platform-button")
        .filter(has_text=re.compile(r"^\s*(?:Добавить|Add)(?:\s*\(\d+\))?\s*$", re.I))
        .first
    )
    await expect(confirm).to_be_visible(timeout=30_000)
    await confirm.locator("button").first.click(no_wait_after=True)
    await expect(picker).to_be_hidden(timeout=30_000)


async def flows_e2e_expect_skill_load_chip(page: Page, skill_name: str) -> Locator:
    # chat-page — основной чат агента; Lara FAB часто attached в DOM и перехватывает поиск.
    chat = page.locator("chat-page platform-flow-ui").first
    if await chat.count() == 0:
        chat = page.locator('platform-flow-ui[flow-id="lara"]').first
    if await chat.count() == 0:
        chat = page.locator("platform-flow-ui").first
    chip = chat.get_by_role(
        "group",
        name=re.compile(
            rf"(?:Activated skills|Активированн\w* Skill)[s]?:.*{re.escape(skill_name)}",
            re.I,
        ),
    ).first
    if await chip.count() == 0:
        chip = chat.get_by_text(re.compile(rf"Skill\s*[«\"]?{re.escape(skill_name)}", re.I)).first
    await expect(chip).to_be_visible(timeout=120_000)
    return chip


async def flows_e2e_expect_reflection_chip(
    page: Page,
    *,
    exit_label: str = "Blocked",
    chat: Locator | None = None,
) -> Locator:
    """Чип резолюции reflection gate на assistant-bubble."""
    host = chat
    if host is None:
        host = page.locator("flows-execution-panel platform-flow-ui").first
        if await host.count() == 0:
            host = page.locator("chat-page platform-flow-ui").first
        if await host.count() == 0:
            host = page.locator("platform-flow-ui").first
    group = host.get_by_role(
        "group",
        name=re.compile(
            rf"(?:Quality checks|Проверки качества):\s*.*{re.escape(exit_label)}",
            re.I,
        ),
    ).first
    await expect(group).to_be_visible(timeout=120_000)
    chip = group.locator("button.reflection-chip").first
    await expect(chip).to_be_visible(timeout=15_000)
    return chip


async def flows_e2e_open_lara_chat(page: Page, flows_ui: AppUI) -> None:
    """Открывает глобальный drawer Lara через FAB на главной Flows."""
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    chat = page.locator('platform-flow-ui[flow-id="lara"]').first
    await expect(chat).to_be_attached(timeout=30_000)
    fab = chat.locator("button.launcher, button.fab").first
    await expect(fab).to_be_visible(timeout=30_000)
    await fab.click()
    await expect(chat).to_have_attribute("open", "", timeout=15_000)
    composer = chat.locator(FLOW_UI_COMPOSER_SELECTOR).first
    await expect(composer).to_be_visible(timeout=30_000)


async def flows_e2e_open_chat_settings(page: Page) -> Locator:
    """Открывает настройки агента и возвращает блок chat settings."""
    modal = await flows_open_flow_edit_modal(page)
    settings = modal.locator("flow-ui-policy-fields").first
    await expect(settings).to_be_visible(timeout=30_000)
    return settings


async def flows_e2e_set_show_skill_loads(page: Page, *, enabled: bool) -> None:
    settings = await flows_e2e_open_chat_settings(page)
    field = settings.locator('platform-field[data-chat-field="show_skill_loads"]').first
    await expect(field).to_be_visible(timeout=15_000)
    await field.evaluate(
        """
        (el, enabled) => {
            el.value = enabled;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: enabled },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        enabled,
    )


async def flows_e2e_set_show_reflection(page: Page, *, enabled: bool) -> None:
    settings = await flows_e2e_open_chat_settings(page)
    field = settings.locator('platform-field[data-chat-field="show_reflection"]').first
    await expect(field).to_be_visible(timeout=15_000)
    await field.evaluate(
        """
        (el, enabled) => {
            el.value = enabled;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: enabled },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        enabled,
    )


async def flows_llm_add_named_tool_from_library(page: Page, tool_name: str) -> None:
    llm_editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor"
    ).first
    await expect(llm_editor).to_be_visible(timeout=30_000)
    await flows_click_platform_button(llm_editor, "Из библиотеки", "From library")
    await flows_pick_library_card_by_text(page, tool_name)


async def flows_e2e_ensure_platform_skills_seed(origin: str, auth_token: str) -> None:
    """Idempotent POST ensure-seed for platform Agent Skills (incl. agent-planning)."""
    async with _flows_client(origin, auth_token) as client:
        response = await client.post("/flows/api/v1/agent-skills/ensure-seed", json={})
    if response.status_code not in (200, 201):
        raise AssertionError(f"ensure-seed failed: {response.status_code} {response.text}")


async def flows_e2e_open_studio_skills_tools(page: Page) -> Locator:
    """Открывает секцию Skills/Tools в Studio и включает режим Tools."""
    studio = page.locator("flows-agent-focus-studio").first
    await expect(studio).to_be_visible(timeout=5_000)
    skills_tab = (
        studio.locator("platform-segmented-control")
        .get_by_role("button", name=re.compile(r"Skills|Tools|Инструмент", re.I))
        .first
    )
    await expect(skills_tab).to_be_visible(timeout=5_000)
    if await skills_tab.get_attribute("aria-pressed") != "true":
        await skills_tab.click()
    await flows_e2e_set_llm_output_mode(page, "tools")
    return studio


async def flows_e2e_create_agent_from_react_template(
    page: Page,
    flows_ui: AppUI,
    *,
    flow_id: str,
    name: str = GREEN_GARDEN_AGENT_NAME,
    description: str = "Помощник интернет-магазина садовых товаров",
) -> None:
    """Мастер создания агента (шаблон react) → студия или канва."""
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    create_button = page.locator("flows-catalog-list [data-action='create-flow']").first
    await expect(create_button).to_be_visible(timeout=30_000)
    await create_button.click()
    modal = page.locator("flows-flow-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    preset = modal.locator("platform-picker-card[value='react']").first
    await expect(preset).to_be_visible(timeout=15_000)
    await preset.click()
    fields = modal.locator("platform-field")
    await expect(fields.first).to_be_visible(timeout=15_000)
    await flows_set_platform_field(fields.nth(0), flow_id)
    if await fields.count() > 1:
        await flows_set_platform_field(fields.nth(1), name)
    if await fields.count() > 2:
        await flows_set_platform_field(fields.nth(2), description)
    await flows_click_platform_button(modal, "Создать", "Create", "Готово", "Done")
    studio_sections = page.get_by_role("group", name=re.compile(r"Agent editor sections", re.I))
    canvas = page.locator("flows-flow-canvas").first
    try:
        await expect(studio_sections.first).to_be_visible(timeout=15_000)
    except AssertionError:
        await expect(canvas.locator("svg.canvas-host")).to_be_visible(timeout=30_000)
        await flows_e2e_switch_editor_layout(page, "agent")
        await expect(studio_sections.first).to_be_visible(timeout=30_000)


async def flows_e2e_expect_agent_plan_block(
    page: Page,
    *,
    completed_title: str,
    in_progress_title: str | None = None,
    chat_selector: str = "chat-page platform-flow-ui",
) -> Locator:
    """Ждёт checklist AgentPlan в чате: completed (+ опционально in_progress)."""
    chat = page.locator(chat_selector).first
    await expect(chat).to_be_visible(timeout=30_000)
    plan_host = chat.locator("platform-agent-plan").last
    await expect(plan_host).to_be_visible(timeout=90_000)
    completed = (
        plan_host.locator('.row[data-status="completed"]')
        .filter(has_text=re.compile(re.escape(completed_title), re.I))
        .first
    )
    await expect(completed).to_be_visible(timeout=30_000)
    if in_progress_title is not None:
        active = (
            plan_host.locator('.row[data-status="in_progress"]')
            .filter(has_text=re.compile(re.escape(in_progress_title), re.I))
            .first
        )
        await expect(active).to_be_visible(timeout=15_000)
    return plan_host


def flows_e2e_agent_plan_mock_writes(
    *,
    step1: str,
    step2: str,
    step3: str,
    final_text: str,
    load_skill_id: str | None = None,
) -> list[dict[str, Any]]:
    """MockLLM: optional load_agent_skill + два agent_plan_write + финальный text."""
    responses: list[dict[str, Any]] = []
    if load_skill_id is not None:
        responses.append(
            {
                "type": "tool_call",
                "tool": "load_agent_skill",
                "args": {"agent_skill_id": load_skill_id},
            }
        )
    responses.extend(
        [
            {
                "type": "tool_call",
                "tool": "agent_plan_write",
                "args": {
                    "steps": [
                        {"id": "1", "title": step1, "status": "in_progress"},
                        {"id": "2", "title": step2, "status": "pending"},
                        {"id": "3", "title": step3, "status": "pending"},
                    ]
                },
            },
            {
                "type": "tool_call",
                "tool": "agent_plan_write",
                "args": {
                    "steps": [
                        {"id": "1", "title": step1, "status": "completed"},
                        {"id": "2", "title": step2, "status": "in_progress"},
                        {"id": "3", "title": step3, "status": "pending"},
                    ]
                },
            },
            {"type": "text", "content": final_text},
        ]
    )
    return responses

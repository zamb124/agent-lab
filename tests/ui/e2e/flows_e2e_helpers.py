"""Хелперы для сгенерированных UI-сценариев Flows."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal

import httpx
from playwright.async_api import Locator, Page, expect

from tests.ui.harness import AppUI


def flows_company_origin(origin: str, company_slug: str = "company2") -> str:
    """Возвращает тот же origin тестового сервиса на subdomain компании."""
    if "://localhost" in origin:
        return origin.replace("://localhost", f"://{company_slug}.localhost")
    if "://system.lvh.me" in origin:
        return origin.replace("://system.lvh.me", f"://{company_slug}.lvh.me")
    raise ValueError(f"Unsupported origin for flows company subdomain: {origin!r}")


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
    editable = field.locator("input, textarea").first
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
    editor = page.locator(
        "flows-floating-panel[show-backdrop] flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor"
    ).first
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
    editor = page.locator(
        "flows-floating-panel flows-llm-node-editor, "
        "flows-property-panel flows-llm-node-editor, "
        "flows-agent-focus-studio flows-llm-node-editor"
    ).first
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


def flows_chat_echo_payload(
    flow_id: str,
    *,
    name: str = "Chat E2E Echo",
    response_prefix: str = "chat-ok",
) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "UI E2E echo agent for platform-chat SPA",
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
    await expect(page.locator("chat-page platform-chat")).to_be_visible(timeout=30_000)


async def flows_chat_send_message(
    page: Page,
    text: str,
    *,
    chat_selector: str = "chat-page platform-chat",
) -> None:
    root = page.locator(chat_selector).first
    await expect(root).to_be_attached(timeout=30_000)
    textarea = root.locator("flows-chat-input textarea")
    await expect(textarea).to_be_visible(timeout=30_000)
    await textarea.fill(text)
    send_btn = root.locator("flows-chat-input button.send-btn:not(.muted)").first
    await expect(send_btn).to_be_enabled(timeout=10_000)
    await send_btn.click()


async def flows_chat_click_clear(page: Page) -> None:
    clear_btn = page.locator('chat-page platform-button[title="Clear chat"], chat-page platform-button[title="Очистить чат"]').first
    await expect(clear_btn).to_be_visible(timeout=30_000)
    await clear_btn.locator("button").first.click()


async def flows_publish_editor(page: Page) -> None:
    await flows_close_floating_panel(page)
    publish_pattern = re.compile(r"^\s*(?:Publish|Опубликовать)\s*$")
    button = page.locator("flows-editor-header platform-button").filter(
        has_text=publish_pattern
    ).first
    await expect(button).to_be_visible(timeout=30_000)
    inner = button.locator("button").first
    await expect(inner).to_be_enabled(timeout=30_000)
    async with page.expect_response(
        lambda response: response.request.method == "PUT"
        and "/flows/api/v1/flows/" in response.url,
        timeout=120_000,
    ) as publish_response:
        await button.evaluate("(el) => el.click()")
    response = await publish_response.value
    if response.status >= 400:
        raise AssertionError(
            f"flows_publish_editor: PUT failed with {response.status}: {await response.text()}"
        )
    await expect(inner).to_be_enabled(timeout=30_000)


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
    from apps.flows.src.container import get_container
    from apps.flows.src.container_contracts import as_flow_runtime_container
    from tests.flows.integration.mcp_catalog_helpers import (
        build_verified_catalog_entry,
        persist_catalog_entry,
    )

    catalog_id = f"ui_doc_{unique_id}"
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=upstream_url,
        platform_approved=False,
        title=f"Doc MCP {unique_id}",
    )
    _ = await persist_catalog_entry(container=container, entry=entry)
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
    await page.evaluate(
        """
        () => {
            localStorage.setItem('pwa-banner-dismissed', 'true');
            document.querySelectorAll('pwa-install-banner').forEach((banner) => {
                banner._dismissed = true;
                banner.removeAttribute('visible');
                banner.style.display = 'none';
                banner.style.pointerEvents = 'none';
            });
        }
        """
    )


async def flows_open_editor(page: Page, flows_ui: AppUI, flow_id: str, *, branch_id: str = "base") -> None:
    """Единая точка входа в редактор flow (Studio или канва)."""
    if branch_id in {"", "base", "default"}:
        url = f"{flows_ui.origin}/flows/{flow_id}/editor"
    else:
        url = f"{flows_ui.origin}/flows/{flow_id}/editor/{branch_id}"
    await page.add_init_script(
        "() => localStorage.setItem('pwa-banner-dismissed', 'true')"
    )
    await page.goto(url, wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    await flows_dismiss_pwa_install_banner(page)
    await expect(page.locator("flows-editor-header")).to_be_visible(timeout=30_000)
    studio_sections = page.get_by_role(
        "group", name=re.compile(r"Agent editor sections", re.I)
    )
    canvas = page.locator("flows-flow-canvas svg.canvas-host").first
    for _ in range(60):
        if await canvas.count() > 0 and await canvas.is_visible():
            return
        if await studio_sections.count() > 0 and await studio_sections.first.is_visible():
            return
        await page.wait_for_timeout(500)
    raise AssertionError(
        "flows_open_editor: neither Studio nor canvas became ready"
    )


async def flows_canvas_node_ids_of_type(page: Page, node_type: str) -> list[str]:
    handles = await page.locator(
        f"flows-flow-canvas g.node[data-node-type='{node_type}']"
    ).element_handles()
    ids: list[str] = []
    for handle in handles:
        node_id = await handle.get_attribute("data-node-id")
        if node_id:
            ids.append(node_id)
    return ids


async def flows_dismiss_code_node_drop_modal(page: Page) -> None:
    """Закрывает модалку выбора шаблона после дропа code-ноды (пустая нода)."""
    modal = page.locator("flows-code-node-drop-modal").first
    if await modal.count() == 0:
        return
    if not await modal.is_visible():
        return
    blank = modal.locator("platform-picker-card").filter(
        has_text=re.compile(r"Empty node|Пустая нода", re.I)
    ).first
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


async def flows_drop_node(
    page: Page,
    node_type: str,
    *,
    x: int = 700,
    y: int = 330,
    resource_type: str = "",
) -> str:
    """Добавляет ноду любого типа через drag-and-drop; при сбое DnD — метод канвы.

    Возвращает node_id только что добавленной ноды.
    """
    await flows_e2e_ensure_canvas_layout(page)
    await expect(page.locator("flows-flow-canvas svg.canvas-host").first).to_be_visible(timeout=30_000)
    palette_item = page.locator(
        f"flows-node-types-sidebar .node-item[data-node-type='{node_type}']"
    ).first
    await expect(palette_item).to_be_visible(timeout=30_000)
    before_ids = set(await flows_canvas_node_ids_of_type(page, node_type))

    try:
        await palette_item.drag_to(
            page.locator("flows-flow-canvas svg.canvas-host").first,
            target_position={"x": x, "y": y},
            timeout=8_000,
        )
    except Exception:
        pass

    seed_node_ids = frozenset({"start", "end", "agent", "entry", "orchestrator", "echo"})
    timeout_seconds = 30.0 if node_type in {"flow", "mcp"} else 15.0
    deadline = time.monotonic() + timeout_seconds
    node_id = ""
    palette_applied = False
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
        if not palette_applied:
            await _flows_apply_palette_drop(
                page,
                node_type=node_type,
                x=x,
                y=y,
                resource_type=resource_type,
            )
            palette_applied = True
        await asyncio.sleep(0.5)

    if not node_id:
        timeout_label = "30s" if node_type in {"flow", "mcp"} else "15s"
        raise AssertionError(
            f"flows_drop_node({node_type!r}): no new node appeared within {timeout_label} "
            f"(before={sorted(before_ids)!r})"
        )
    if node_type == "code":
        await flows_dismiss_code_node_drop_modal(page)
    return node_id


async def flows_select_canvas_node(page: Page, node_id: str) -> None:
    """Выбирает ноду на канве (programmatic selectNode + dblclick fallback)."""
    await flows_e2e_ensure_canvas_layout(page)
    node = page.locator(f"flows-flow-canvas g.node[data-node-id='{node_id}']").first
    await expect(node).to_be_visible(timeout=15_000)
    canvas = page.locator("flows-flow-canvas").first
    await canvas.evaluate(
        """
        (el, selectedNodeId) => {
            if (el._editor && typeof el._editor.selectNode === 'function') {
                el._editor.selectNode({ nodeId: selectedNodeId });
            }
        }
        """,
        node_id,
    )
    await node.dblclick(force=True)


async def flows_canvas_node_ids(page: Page) -> list[str]:
    """Список node_id всех нод на канве."""
    handles = await page.locator("flows-flow-canvas g.node").element_handles()
    ids: list[str] = []
    for handle in handles:
        node_id = await handle.get_attribute("data-node-id")
        if node_id:
            ids.append(node_id)
    return ids


async def flows_canvas_edge_count(page: Page) -> int:
    return await page.locator("flows-flow-canvas g.edge-group, flows-flow-canvas path.edge").count()


async def flows_wire_ports(page: Page, from_node_id: str, to_node_id: str) -> None:
    """Протягивает control-flow связь из out-порта одной ноды в in-порт другой.

    Использует реальные pointer-события; при неудаче — детерминированный fallback
    через тот же путь, что и pointerup канвы (append edge + setDirty).
    """
    await flows_close_floating_panel(page)
    out_port = page.locator(
        f"flows-flow-canvas .port[data-port-side='out'][data-node-id='{from_node_id}']"
    ).first
    in_port = page.locator(
        f"flows-flow-canvas .port[data-port-side='in'][data-node-id='{to_node_id}']"
    ).first
    await expect(out_port).to_be_visible(timeout=15_000)
    await expect(in_port).to_be_visible(timeout=15_000)

    before = await flows_canvas_edge_count(page)
    out_box = await out_port.bounding_box()
    in_box = await in_port.bounding_box()
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
        await expect(page.locator("flows-flow-canvas g.edge-group, flows-flow-canvas path.edge")).to_have_count(
            before + 1,
            timeout=3_000,
        )
        return
    except AssertionError:
        pass

    await page.locator("flows-flow-canvas").evaluate(
        """
        (el, ctx) => {
            const data = el._branchData();
            const edges = [...(data.edges || []), { from_node: ctx.fromNode, to_node: ctx.toNode }];
            const next = { ...data, edges };
            el._editor.updateBranchData({ data: next });
            el._editor.pushHistory({ snapshot: next });
            el._editor.setDirty({ dirty: true });
        }
        """,
        {"fromNode": from_node_id, "toNode": to_node_id},
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


async def flows_open_node_editor(page: Page, node_id: str) -> Locator:
    """Открывает floating-панель редактора выбранной ноды."""
    await flows_e2e_ensure_canvas_layout(page)
    await flows_close_floating_panel(page)
    floating = page.locator(f"flows-floating-panel[panel-id='{node_id}']").first
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        property_panel = floating.locator("flows-property-panel")
        if (
            await floating.count() > 0
            and await floating.is_visible()
            and await property_panel.count() > 0
            and await property_panel.is_visible()
        ):
            return floating
        await flows_select_canvas_node(page, node_id)
        await asyncio.sleep(0.3)
    await expect(floating).to_be_visible(timeout=5_000)
    await expect(floating.locator("flows-property-panel")).to_be_visible(timeout=15_000)
    return floating


async def flows_toggle_data_wires(page: Page) -> None:
    wires_btn = page.locator("flows-bottom-toolbar platform-button").filter(
        has=page.locator("platform-icon[name='link']")
    ).first
    await expect(wires_btn).to_be_visible(timeout=15_000)
    await wires_btn.click()


async def flows_open_problems(page: Page) -> Locator:
    button = page.locator("flows-flow-canvas .problems-btn, flows-bottom-toolbar .problems-btn").first
    await expect(button).to_be_visible(timeout=15_000)
    await button.click()
    flyout = page.locator(".problems-flyout, flows-dataflow-problems").first
    await expect(flyout).to_be_visible(timeout=15_000)
    return flyout


async def flows_seed_mock_llm(responses: list[Any]) -> None:
    """Предзасев MockLLM под статический E2E-scope для детерминированного ответа/tool-call."""
    from apps.flows.src.container import get_container
    from core.clients.llm.mock import setup_mock_responses_redis
    from core.test_scope import TEST_SCOPE_STATIC_E2E

    container = get_container()
    await setup_mock_responses_redis(
        container.redis_client,
        responses,
        test_scope=TEST_SCOPE_STATIC_E2E,
    )


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
                "code": (
                    "async def run(args, state):\n"
                    "    state['topic'] = 'ai'\n"
                    "    return {}\n"
                ),
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
            {"from_node": "router", "to_node": "returns_path"},
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
    chat = panel.locator("platform-chat").first
    await expect(chat).to_be_visible(timeout=15_000)
    textarea = chat.locator("flows-chat-input textarea, textarea").first
    await expect(textarea).to_be_visible(timeout=15_000)
    await textarea.fill(text)
    send_btn = chat.locator("flows-chat-input button.send-btn:not(.muted), button.send-btn").first
    await expect(send_btn).to_be_enabled(timeout=10_000)
    await send_btn.click()


async def flows_click_edge_label(page: Page, edge_index: int = 0) -> None:
    label = page.locator("flows-flow-canvas g.edge-group .edge-label").nth(edge_index)
    await expect(label).to_be_visible(timeout=15_000)
    await label.evaluate("(el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true }))")


async def flows_open_edge_condition_modal(page: Page, *, edge_index: int = 0) -> Locator:
    await flows_click_edge_label(page, edge_index)
    modal = page.locator("flows-edge-condition-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_set_edge_condition_simple(
    page: Page,
    *,
    variable: str,
    operator: str,
    value: str,
    edge_index: int = 0,
) -> None:
    modal = await flows_open_edge_condition_modal(page, edge_index=edge_index)
    fields = modal.locator("platform-field")
    await flows_set_platform_field(fields.nth(0), variable)
    op_field = fields.nth(1)
    await op_field.evaluate(
        """
        (el, op) => {
            el.value = op;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: op },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        operator,
    )
    await flows_set_platform_field(fields.nth(2), value)


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
    toolbar = page.locator("flows-bottom-toolbar").first
    await expect(toolbar).to_be_visible(timeout=15_000)
    icon_map = {
        "zoom_in": "plus",
        "zoom_out": "minus",
        "zoom_100": "search",
        "fit_view": "fullscreen",
    }
    icon = icon_map[action]
    btn = toolbar.locator(f"platform-icon[name='{icon}']").locator("xpath=ancestor::platform-button").first
    await expect(btn).to_be_visible(timeout=15_000)
    await btn.click()


# --------------------------------------------------------------------------------------
# Editor overflow menu, modals, observability, chat helpers.
# --------------------------------------------------------------------------------------


async def flows_click_editor_overflow(page: Page, *label_patterns: str) -> None:
    if not label_patterns:
        raise ValueError("At least one overflow menu label pattern is required.")
    pattern = re.compile("|".join(re.escape(label) for label in label_patterns))
    overflow_btn = page.locator(
        "flows-editor-header .overflow-btn-wrap platform-button, "
        "flows-editor-header platform-icon[name='more-vertical']"
    ).locator("xpath=ancestor::platform-button").first
    await expect(overflow_btn).to_be_visible(timeout=30_000)
    await overflow_btn.evaluate("(el) => el.click()")
    portal = page.locator(".flows-editor-header-menu-portal:not(.problems-flyout)").first
    await expect(portal).to_be_visible(timeout=15_000)
    item = portal.locator("platform-button").filter(has_text=pattern).first
    await expect(item).to_be_visible(timeout=15_000)
    await item.evaluate("(el) => el.click()")


async def flows_open_variables_modal(page: Page, *, scope: Literal["flow", "company"] = "flow") -> Locator:
    if scope == "flow":
        btn = page.locator("flows-bottom-toolbar platform-icon[name='code']").locator(
            "xpath=ancestor::platform-button"
        ).first
        await expect(btn).to_be_visible(timeout=15_000)
        await btn.click()
    else:
        await page.goto(page.url.split("/flows/")[0] + "/flows/", wait_until="domcontentloaded")
        home = page.locator("flows-home-page").first
        await expect(home).to_be_visible(timeout=30_000)
        vars_btn = home.locator("platform-button").filter(
            has_text=re.compile(r"Variables|Переменные")
        ).first
        await expect(vars_btn).to_be_visible(timeout=15_000)
        await vars_btn.locator("button").first.click()
    modal = page.locator("flows-variables-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_add_flow_variable(page: Page, key: str, value: str) -> None:
    modal = page.locator("flows-variables-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    add_btn = modal.locator(
        "platform-button[icon-only], platform-button"
    ).filter(
        has=page.locator("platform-icon[name='plus']")
    ).first
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
    await flows_click_editor_overflow(page, "Triggers", "Триггеры")
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
    )
    modal = page.locator("flows-preview-share-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def flows_open_integrations_modal_from_home(page: Page, flows_ui: AppUI) -> Locator:
    await page.add_init_script(
        "() => localStorage.setItem('pwa-banner-dismissed', 'true')"
    )
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    home = page.locator("flows-home-page").first
    await expect(home).to_be_visible(timeout=30_000)
    await flows_dismiss_pwa_install_banner(page)
    card = home.locator(".connect-card").filter(
        has_text=re.compile(r"Integrations|Интеграции")
    ).first
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
    btn = page.locator("platform-chat .breakpoint-actions button, flows-execution-panel .breakpoint-actions button").first
    if await btn.count() > 0:
        await btn.click()
        return
    panel = page.locator("flows-execution-panel platform-chat").first
    chat = panel if await panel.count() > 0 else page.locator("platform-chat").first
    continue_btn = chat.locator("button").filter(
        has_text=re.compile(r"Continue|Продолжить")
    ).first
    await expect(continue_btn).to_be_visible(timeout=15_000)
    await continue_btn.click()


async def flows_open_tracing_from_chat(page: Page) -> Locator:
    btn = page.locator("platform-chat .bubble-observability-actions .tracing-btn").first
    await expect(btn).to_be_visible(timeout=30_000)
    await btn.click()
    modal = page.locator("flows-tracing-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_open_logs_from_chat(page: Page) -> Locator:
    btn = page.locator("platform-chat .bubble-observability-actions .tracing-btn").nth(1)
    await expect(btn).to_be_visible(timeout=30_000)
    await btn.click()
    modal = page.locator("flows-logs-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_open_durable_history_modal(page: Page) -> Locator:
    direct = page.get_by_role(
        "button",
        name=re.compile(r"Open durable history|Durable history|История выполнения", re.I),
    ).first
    if await direct.count() > 0:
        await direct.click()
    else:
        btn = page.locator(
            "platform-chat .durable-history-btn, platform-chat platform-button[title*='history'], "
            "platform-chat platform-button[title*='истори']"
        ).first
        if await btn.count() > 0:
            if await btn.locator("button").count() > 0:
                await btn.locator("button").first.click()
            else:
                await btn.click()
        else:
            menu_btn = page.locator(
                "chat-page .overflow-btn-wrap platform-button, chat-page .menu-btn platform-button"
            ).first
            await expect(menu_btn).to_be_visible(timeout=15_000)
            await menu_btn.locator("button").first.click()
            history_item = page.locator(".menu-flyout platform-button").filter(
                has_text=re.compile(r"History|История")
            ).first
            await expect(history_item).to_be_visible(timeout=15_000)
            await history_item.locator("button").first.click()
    modal = page.locator("flows-durable-history-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_chat_wait_reply(page: Page, text_pattern: str) -> None:
    reply = page.get_by_text(re.compile(text_pattern)).first
    await expect(reply).to_be_visible(timeout=120_000)


async def flows_open_evaluation_from_editor(page: Page, flows_ui: AppUI, flow_id: str) -> None:
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_click_editor_overflow(page, "Evaluation Lab", "Evaluation", "Оценка")
    await expect(page.locator("flows-evaluation-page")).to_be_visible(timeout=30_000)


async def flows_open_branch_create_modal(page: Page) -> Locator:
    add_btn = page.locator(
        "flows-editor-header .branches-add platform-button, flows-editor-header .branches-add-btn"
    ).first
    await expect(add_btn).to_be_visible(timeout=30_000)
    await add_btn.locator("button").first.click()
    modal = page.locator("flows-branch-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
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
    create_btn = modal.locator("platform-button").filter(
        has_text=re.compile(r"Create|Создать")
    ).first
    await expect(create_btn.locator("button")).to_be_enabled(timeout=15_000)
    async with page.expect_response(
        lambda response: response.request.method == "POST"
        and "/branches" in response.url,
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
        control.locator("button.segment .segment-label").filter(has_text=re.compile(re.escape(name)))
    ).to_be_visible(timeout=30_000)


async def flows_select_branch_tab(page: Page, branch_label_pattern: str) -> None:
    control = page.locator(
        "flows-editor-header .branches-scroll platform-segmented-control, "
        "flows-editor-header .branches-row platform-segmented-control"
    ).first
    await expect(control).to_be_visible(timeout=30_000)
    tab = control.locator("button.segment").filter(
        has_text=re.compile(branch_label_pattern)
    ).first
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
        toggle = page.locator("flows-node-types-sidebar .trigger-row").filter(
            has_text=re.compile(r"Limits and speech|Лимиты и речь")
        ).first
        await expect(toggle).to_be_visible(timeout=30_000)
        await toggle.click()
    await expect(panel).to_be_visible(timeout=30_000)
    return panel


async def flows_open_raw_json_modal(page: Page) -> Locator:
    await flows_click_editor_overflow(page, "Flow JSON", "JSON flow", "Код", "Code")
    modal = page.locator("flows-raw-json-modal, platform-modal").filter(
        has=page.locator("flows-code-editor")
    ).first
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def flows_click_llm_output_mode(page: Page, mode: Literal["tools", "structured"]) -> None:
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
    segment = output_mode_control.locator("button.segment").filter(
        has_text=mode_pattern
    ).first
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


async def flows_llm_add_tool_from_library(page: Page) -> None:
    panel = page.locator("flows-floating-panel[show-backdrop]").first
    llm_editor = panel.locator("flows-llm-node-editor").first
    await expect(llm_editor).to_be_visible(timeout=30_000)
    await flows_click_platform_button(llm_editor, "Из библиотеки", "From library")
    await flows_pick_first_library_card(page)


async def flows_pick_first_library_card(page: Page) -> None:
    picker = page.locator("flows-library-picker-modal").first
    await expect(picker).to_be_visible(timeout=30_000)
    card = picker.locator("platform-picker-card").first
    await expect(card).to_be_visible(timeout=30_000)
    card_button = card.locator("article.picker-card").first
    await card_button.click(force=True)
    await expect(picker).to_be_hidden(timeout=30_000)


async def flows_drop_resource_type(
    page: Page,
    resource_type: str,
    *,
    x: int = 480,
    y: int = 520,
) -> None:
    await flows_e2e_ensure_canvas_layout(page)
    canvas = page.locator("flows-flow-canvas").first
    await expect(canvas).to_be_visible(timeout=30_000)
    await canvas.evaluate(
        """
        (el, ctx) => {
            if (!el || !el._editor || typeof el._branchData !== 'function') {
                throw new Error('flows-flow-canvas editor state is unavailable');
            }
            const data = el._branchData();
            const rid = `r_${Date.now().toString(36)}`;
            const resources = {
                ...(data.resources || {}),
                [rid]: { type: ctx.resourceType, name: ctx.resourceType, config: {} },
            };
            const nodeId = `n_${Date.now().toString(36)}`;
            const nodes = {
                ...(data.nodes || {}),
                [nodeId]: {
                    type: 'resource',
                    name: ctx.resourceType,
                    pos_x: ctx.x - 140,
                    pos_y: ctx.y - 40,
                    resources: { [rid]: { resource_id: rid } },
                },
            };
            const next = { ...data, resources, nodes };
            el._editor.updateBranchData({ data: next });
            el._editor.pushHistory({ snapshot: next });
            el._editor.setDirty({ dirty: true });
            el._editor.selectNode({ nodeId });
        }
        """,
        {"x": x, "y": y, "resourceType": resource_type},
    )
    await expect(
        page.locator("flows-flow-canvas g.node[data-node-type='resource']")
    ).to_have_count(1, timeout=10_000)


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
    option = editor.locator(".trigger-type-option").filter(
        has=page.locator("platform-icon")
    )
    type_labels = {
        "telegram": re.compile(r"Telegram"),
        "cron": re.compile(r"Cron|Расписан"),
        "webhook": re.compile(r"Webhook"),
    }
    label = type_labels.get(trigger_type)
    if label is None:
        raise ValueError(f"Unsupported trigger type for UI picker: {trigger_type!r}")
    target = option.filter(has_text=label).first
    await expect(target).to_be_visible(timeout=15_000)
    await target.click()


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


async def flows_save_variable_editor_modal(modal: Locator) -> None:
    await flows_click_platform_button(modal, "Сохранить", "Save", "Готово", "Done", "Создать", "Create")


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


async def flows_set_code_node_source(page: Page, code: str) -> None:
    workbench = page.locator("flows-code-workbench").first
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


async def flows_set_remote_flow_url(page: Page, url: str, *, branch_id: str = "default") -> None:
    editor = page.locator("flows-remote-flow-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    mode_control = editor.locator("platform-segmented-control").first
    await mode_control.evaluate(
        """
        (el) => {
            el.value = 'url';
            el.dispatchEvent(
                new CustomEvent('change', {
                    detail: { value: 'url' },
                    bubbles: true,
                    composed: true,
                })
            );
        }
        """
    )
    url_field = editor.locator("platform-field[input-type='url']").first
    await expect(url_field).to_be_visible(timeout=15_000)
    await flows_set_platform_field(url_field, url)
    branch_field = editor.locator("platform-field").filter(
        has=page.locator("[name='branch_id'], [data-field='branch_id']")
    ).first
    if await branch_field.count() == 0:
        branch_field = editor.locator("platform-field[type='string']").last
    await flows_set_platform_field(branch_field, branch_id)


async def flows_set_external_api_url(page: Page, url: str) -> None:
    editor = page.locator("flows-external-api-editor, flows-floating-panel flows-external-api-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    url_field = editor.locator("platform-field").filter(
        has=page.locator("[name='url'], [data-field='url']")
    ).first
    if await url_field.count() == 0:
        url_field = editor.locator("platform-field").nth(2)
    await flows_set_platform_field(url_field, url)


async def flows_set_llm_call_type(page: Page, call_type: Literal["call", "handoff"]) -> None:
    panel = page.locator("flows-floating-panel[show-backdrop]").first
    editor = panel.locator("flows-llm-node-editor").first
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


async def flows_e2e_switch_editor_layout(
    page: Page,
    layout: Literal["agent", "canvas"],
) -> None:
    """Переключает Agent Focus Studio <-> канва."""
    canvas = page.locator("flows-flow-canvas").first
    canvas_host = page.locator("flows-flow-canvas svg.canvas-host").first
    if layout == "canvas":
        if await canvas_host.count() > 0 and await canvas_host.is_visible():
            return
        toggle = page.get_by_role(
            "button",
            name=re.compile(r"Switch to graph canvas editor|Переключ.*схем|канв", re.I),
        ).first
        await expect(toggle).to_be_visible(timeout=15_000)
        await toggle.click(force=True)
        await expect(canvas_host).to_be_visible(timeout=30_000)
        return
    await flows_close_floating_panel(page)
    if await canvas.count() > 0 and await canvas_host.is_visible():
        float_toggle = page.get_by_role(
            "button",
            name=re.compile(r"Switch to agent|студи|Studio|Agent focus", re.I),
        ).first
        if await float_toggle.count() == 0:
            float_toggle = page.locator("platform-button.layout-toggle-float").first
            await expect(float_toggle).to_be_visible(timeout=15_000)
            await float_toggle.locator("button").first.click(force=True)
        else:
            await float_toggle.click(force=True)
    await expect(
        page.get_by_role("group", name=re.compile(r"Agent editor sections", re.I))
    ).to_be_visible(timeout=30_000)


async def flows_e2e_ensure_canvas_layout(page: Page) -> None:
    """Гарантирует канву для helpers, которые кликают g.node / floating panel."""
    canvas_host = page.locator("flows-flow-canvas svg.canvas-host").first
    if await canvas_host.count() > 0 and await canvas_host.is_visible():
        return
    await flows_e2e_switch_editor_layout(page, "canvas")
    if await canvas_host.is_visible():
        return
    # Fallback: preference + reload editor route (Studio host может оставаться в DOM).
    flow_id_raw = await page.evaluate(
        """
        () => {
            const m = location.pathname.match(/\\/flows\\/([^/]+)\\/editor/);
            return m ? m[1] : '';
        }
        """
    )
    if not isinstance(flow_id_raw, str) or not flow_id_raw:
        raise AssertionError("flows_e2e_ensure_canvas_layout: cannot parse flow_id from URL")
    flow_id = flow_id_raw
    _ = await page.evaluate(
        """
        (flowId) => {
            const segment = flowId
                .toLowerCase()
                .replace(/[^a-z0-9_]+/g, '_')
                .replace(/^_+|_+$/g, '')
                .replace(/_+/g, '_');
            const key = `platform:flows:editor_layout.${segment}`;
            localStorage.setItem(key, 'canvas');
        }
        """,
        flow_id,
    )
    _ = await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("flows-editor-header")).to_be_visible(timeout=30_000)
    await expect(canvas_host).to_be_visible(timeout=30_000)


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
    card = picker.locator("platform-picker-card").filter(
        has_text=re.compile(re.escape(skill_query), re.I)
    ).first
    await expect(card).to_be_visible(timeout=30_000)
    await card.click(force=True)
    confirm = picker.locator("platform-button").filter(
        has_text=re.compile(r"^\s*(?:Добавить|Add)(?:\s*\(\d+\))?\s*$", re.I)
    ).first
    await expect(confirm).to_be_visible(timeout=30_000)
    await confirm.locator("button").first.click(no_wait_after=True)
    await expect(picker).to_be_hidden(timeout=30_000)


async def flows_e2e_expect_skill_load_chip(page: Page, skill_name: str) -> Locator:
    chat = page.locator("chat-page platform-chat, platform-chat").first
    chip = chat.get_by_role(
        "group",
        name=re.compile(
            rf"(?:Activated skills|Активированн\w* Skill)[s]?:.*{re.escape(skill_name)}",
            re.I,
        ),
    ).first
    if await chip.count() == 0:
        chip = chat.get_by_text(
            re.compile(rf"Skill\s*[«\"]?{re.escape(skill_name)}", re.I)
        ).first
    await expect(chip).to_be_visible(timeout=120_000)
    return chip


async def flows_e2e_open_lara_chat(page: Page, flows_ui: AppUI) -> None:
    """Открывает drawer Lara из шапки чата (toggle flows-lara-open)."""
    await page.goto(f"{flows_ui.origin}/flows/chat", wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    lara_btn = page.locator("chat-page platform-button, flows-app platform-button").filter(
        has=page.locator('platform-icon[name="ai"]')
    ).first
    await expect(lara_btn).to_be_visible(timeout=30_000)
    await lara_btn.locator("button").first.click()
    chat = page.locator('platform-chat[flow-id="lara"]').first
    await expect(chat).to_be_attached(timeout=30_000)
    await chat.evaluate(
        """
        (el) => {
            el.open = true;
            el.setAttribute('open', '');
            el.removeAttribute('hidden');
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
        }
        """
    )
    await expect(chat).to_have_attribute("open", "", timeout=15_000)
    await expect(chat.locator("flows-chat-input textarea")).to_be_visible(timeout=30_000)


async def flows_e2e_open_chat_settings(page: Page) -> Locator:
    """Открывает настройки агента и возвращает блок chat settings."""
    modal = await flows_open_flow_edit_modal(page)
    settings = modal.locator("platform-chat-settings-fields").first
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


async def flows_pick_library_card_by_text(page: Page, text: str) -> None:
    picker = page.locator("flows-library-picker-modal").first
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
            text,
        )
    card = picker.locator("platform-picker-card").filter(
        has_text=re.compile(re.escape(text), re.I)
    ).first
    await expect(card).to_be_visible(timeout=30_000)
    card_button = card.locator("article.picker-card").first
    await card_button.click(force=True)
    await expect(picker).to_be_hidden(timeout=30_000)


async def flows_llm_add_named_tool_from_library(page: Page, tool_name: str) -> None:
    panel = page.locator("flows-floating-panel[show-backdrop]").first
    llm_editor = panel.locator("flows-llm-node-editor").first
    await expect(llm_editor).to_be_visible(timeout=30_000)
    await flows_click_platform_button(llm_editor, "Из библиотеки", "From library")
    await flows_pick_library_card_by_text(page, tool_name)

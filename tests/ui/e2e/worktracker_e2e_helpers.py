"""Хелперы для сгенерированных UI-сценариев Worktracker (операторы, HITL)."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from playwright.async_api import Locator, Page, Response, expect

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI

WORKTRACKER_API_PREFIX = "/worktracker/api/v1"
_WORKTRACKER_HTTP_TIMEOUT_SECONDS = 630.0


def worktracker_api_origin(origin: str) -> str:
    """Worktracker API на отдельном порту test stack (9021)."""
    parsed = urlparse(origin)
    if not parsed.hostname:
        raise ValueError(f"Invalid origin for worktracker API: {origin!r}")
    wt_port = SERVICE_UI_REGISTRY["worktracker"].port
    return urlunparse(parsed._replace(netloc=f"{parsed.hostname}:{wt_port}"))


def _worktracker_client(origin: str, auth_token: str) -> httpx.AsyncClient:
    from tests.ui.e2e_worker import ui_e2e_scope_headers

    api_origin = worktracker_api_origin(origin)
    return httpx.AsyncClient(
        base_url=api_origin,
        cookies={"auth_token": auth_token},
        headers=ui_e2e_scope_headers(),
        timeout=_WORKTRACKER_HTTP_TIMEOUT_SECONDS,
    )


async def worktracker_api_create_queue(
    origin: str,
    auth_token: str,
    *,
    name: str,
    slug: str,
    description: str = "",
) -> dict[str, Any]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-queues",
            json={"name": name, "slug": slug, "description": description},
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST work-queues failed: {response.status_code} {response.text}"
        )
    return response.json()


async def worktracker_api_add_queue_member(
    origin: str,
    auth_token: str,
    work_queue_id: str,
    user_id: str,
    *,
    role: str = "member",
) -> None:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-queues/{work_queue_id}/members",
            json={"member": {"actor_kind": "user", "user_id": user_id}, "role": role},
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST queue members failed: {response.status_code} {response.text}"
        )


async def worktracker_api_create_work_item(
    origin: str,
    auth_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.post(f"{WORKTRACKER_API_PREFIX}/work-items", json=payload)
    if response.status_code >= 400:
        raise AssertionError(
            f"POST work-items failed: {response.status_code} {response.text}"
        )
    return response.json()


async def worktracker_api_list_work_items(
    origin: str,
    auth_token: str,
    **params: str,
) -> list[dict[str, Any]]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.get(f"{WORKTRACKER_API_PREFIX}/work-items", params=params)
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("GET work-items must return OffsetPage with items[].")
    return items


async def worktracker_api_get_work_item(
    origin: str,
    auth_token: str,
    work_item_id: str,
) -> dict[str, Any]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.get(f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}")
    response.raise_for_status()
    return response.json()


def worktracker_queue_work_item_payload(
    *,
    title: str,
    work_queue_id: str,
    description: str = "",
    kind: str = "generic",
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "kind": kind,
        "assignment": {"assignee_kind": "queue", "work_queue_id": work_queue_id},
    }


# --------------------------------------------------------------------------------------
# UI-хелперы оператора
# --------------------------------------------------------------------------------------


async def worktracker_open(page: Page, worktracker_ui: AppUI, path: str = "/worktracker/") -> None:
    url = f"{worktracker_ui.origin}{path}"
    await page.goto(url, wait_until="domcontentloaded")
    await expect(page.locator("worktracker-app")).to_be_visible(timeout=30_000)


async def worktracker_open_inbox(page: Page, worktracker_ui: AppUI) -> Locator:
    await worktracker_open(page, worktracker_ui, "/worktracker/")
    inbox = page.locator("worktracker-inbox-page").first
    await expect(inbox).to_be_visible(timeout=30_000)
    return inbox


async def worktracker_open_queues(page: Page, worktracker_ui: AppUI) -> Locator:
    await worktracker_open(page, worktracker_ui, "/worktracker/queues")
    queues = page.locator("worktracker-queues-page").first
    await expect(queues).to_be_visible(timeout=30_000)
    return queues


async def worktracker_open_board(page: Page, worktracker_ui: AppUI) -> Locator:
    await worktracker_open(page, worktracker_ui, "/worktracker/board")
    board = page.locator("worktracker-board-page").first
    await expect(board).to_be_visible(timeout=30_000)
    return board


async def worktracker_open_task_page(
    page: Page,
    worktracker_ui: AppUI,
    work_item_id: str,
) -> Locator:
    await worktracker_open(page, worktracker_ui, f"/worktracker/tasks/{work_item_id}")
    editor = page.locator(f"work-item-detail-editor[work-item-id='{work_item_id}']").first
    await expect(editor).to_be_visible(timeout=30_000)
    return editor


async def worktracker_create_queue_ui(
    page: Page,
    *,
    name: str,
    slug: str,
) -> None:
    queues = page.locator("worktracker-queues-page").first
    await expect(queues).to_be_visible(timeout=30_000)
    await queues.locator("worktracker-icon-action[icon='plus']").first.click()
    form = queues.locator("section.create-card").first
    await expect(form).to_be_visible(timeout=15_000)
    fields = form.locator("platform-field")
    await _set_platform_field(fields.nth(0), name)
    await _set_platform_field(fields.nth(1), slug)
    await form.locator("button.btn-primary").first.click()


async def worktracker_api_create_board(
    origin: str,
    auth_token: str,
    *,
    name: str,
) -> dict[str, Any]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.post(
            f"{WORKTRACKER_API_PREFIX}/boards",
            json={
                "name": name,
                "columns": [
                    {
                        "board_column_id": "todo",
                        "label": "К выполнению",
                        "state": "open",
                        "position": 0,
                    },
                    {
                        "board_column_id": "in_progress",
                        "label": "В работе",
                        "state": "open",
                        "position": 1,
                    },
                ],
            },
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST boards failed: {response.status_code} {response.text}"
        )
    return response.json()


async def worktracker_api_complete_work_item(
    origin: str,
    auth_token: str,
    work_item_id: str,
    *,
    resolution_text: str,
) -> dict[str, Any]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/complete",
            json={"resolution_text": resolution_text},
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST complete failed: {response.status_code} {response.text}"
        )
    return response.json()


async def worktracker_api_reassign_work_item(
    origin: str,
    auth_token: str,
    work_item_id: str,
    assignment: dict[str, Any],
) -> dict[str, Any]:
    async with _worktracker_client(origin, auth_token) as client:
        response = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/assign",
            json={"assignment": assignment},
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST assign failed: {response.status_code} {response.text}"
        )
    return response.json()


async def worktracker_wait_queue_task_id(
    origin: str,
    auth_token: str,
    *,
    title_contains: str,
    timeout_s: float = 120.0,
) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        items = await worktracker_api_list_work_items(
            origin,
            auth_token,
            queue_unclaimed_only="true",
            exclude_terminal="true",
        )
        for item in items:
            if title_contains in str(item.get("title") or ""):
                work_item_id = item.get("work_item_id")
                if isinstance(work_item_id, str) and work_item_id:
                    return work_item_id
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"No queue task with title containing {title_contains!r} within {timeout_s}s"
    )


async def worktracker_inbox_open_task(
    page: Page,
    worktracker_ui: AppUI,
    *,
    title_contains: str,
    origin: str,
    auth_token: str,
) -> str:
    work_item_id = await worktracker_wait_queue_task_id(
        origin,
        auth_token,
        title_contains=title_contains,
    )
    await worktracker_open_task_page(page, worktracker_ui, work_item_id)
    return work_item_id


async def worktracker_claim_task(page: Page, editor: Locator) -> None:
    claim = editor.locator("worktracker-icon-action[icon='user-plus'] button").first
    await expect(claim).to_be_visible(timeout=15_000)
    await claim.click()
    await expect(
        editor.locator("worktracker-icon-action[icon='user-plus']")
    ).to_have_count(0, timeout=20_000)
    await expect(
        editor.get_by_text(re.compile(r"Нужен доступ к очереди|You need queue access"))
    ).to_have_count(0, timeout=20_000)


async def worktracker_add_comment(page: Page, editor: Locator, text: str) -> None:
    composer = editor.locator("worktracker-activity-thread platform-field[data-canon='composer']").first
    await expect(composer).to_be_visible(timeout=15_000)
    await _set_platform_field(composer, text)
    await editor.locator("button.wt-composer-send").first.click()


async def worktracker_complete_task(page: Page, editor: Locator) -> None:
    complete = editor.locator("worktracker-icon-action[icon='check']").first
    await expect(complete).to_be_visible(timeout=15_000)
    await complete.click()


async def _set_platform_field(field: Locator, value: str) -> None:
    await expect(field).to_be_visible(timeout=15_000)
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


async def worktracker_click_nav(page: Page, *labels: str) -> None:
    pattern = re.compile("|".join(re.escape(x) for x in labels))
    nav = page.locator("worktracker-sidebar button.nav-item").filter(has_text=pattern).first
    await expect(nav).to_be_visible(timeout=15_000)
    await nav.click()


# --------------------------------------------------------------------------------------
# Встроенный HITL-чат (platform-flow-ui operator_handoff в карточке задачи)
# --------------------------------------------------------------------------------------


async def worktracker_hitl_embedded_chat(editor: Locator) -> Locator:
    """`<platform-flow-ui profile=operator_handoff>` внутри карточки operator_handoff."""
    chat = editor.locator("section.wt-hitl platform-flow-ui").first
    await expect(chat).to_be_visible(timeout=60_000)
    return chat


async def worktracker_hitl_chat_wait_text(
    editor: Locator,
    text_pattern: re.Pattern[str] | str,
    *,
    timeout_s: float = 120.0,
) -> None:
    chat = await worktracker_hitl_embedded_chat(editor)
    pattern = (
        text_pattern
        if isinstance(text_pattern, re.Pattern)
        else re.compile(re.escape(text_pattern), re.I)
    )
    await expect(chat.get_by_text(pattern).first).to_be_visible(
        timeout=int(timeout_s * 1000)
    )


def _is_hitl_operator_send_http(response: Response) -> bool:
    if response.request.method != "POST":
        return False
    url = response.url
    if "/conversation/messages" in url:
        return True
    return "/work-items/" in url and url.rstrip("/").endswith("/complete")


async def worktracker_hitl_click_send_and_assert_http(page: Page, send_button: Locator) -> None:
    posts: list[str] = []

    def _on_request(request: Any) -> None:
        if request.method == "POST":
            posts.append(f"{request.method} {request.url}")

    page.on("request", _on_request)
    try:
        async with page.expect_response(_is_hitl_operator_send_http, timeout=30_000) as pending:
            await send_button.click()
        response = await pending.value
    except Exception as exc:
        raise AssertionError(
            f"HITL operator send produced no matching POST. POSTs seen: {posts}"
        ) from exc
    finally:
        page.remove_listener("request", _on_request)
    if response.status >= 400:
        body = await response.text()
        raise AssertionError(f"HITL operator send HTTP {response.status}: {body}")


async def worktracker_hitl_chat_send(editor: Locator, text: str) -> None:
    chat = await worktracker_hitl_embedded_chat(editor)
    textarea = chat.locator('textarea[data-canon="composer"]').first
    await expect(textarea).to_be_visible(timeout=30_000)
    await expect(textarea).to_be_editable(timeout=20_000)
    await textarea.click()
    await textarea.fill(text)
    send_btn = chat.locator(
        "button.circle-btn.send:not(.composer-stop):not([disabled]), button.hitl-host-send:not([disabled])"
    ).first
    if await send_btn.count() == 0:
        send_btn = chat.get_by_role(
            "button",
            name=re.compile(
                r"Ответить и завершить|Reply and complete|Отправить|Send|Submit"
            ),
        ).first
    await expect(send_btn).to_be_enabled(timeout=10_000)
    await worktracker_hitl_click_send_and_assert_http(editor.page, send_btn)
    await worktracker_hitl_chat_wait_text(editor, text.strip(), timeout_s=60.0)


async def worktracker_hitl_single_reply_complete(editor: Locator, text: str) -> None:
    """single_reply: Send в platform-flow-ui = complete + closing reply."""
    await worktracker_hitl_chat_send(editor, text)


async def worktracker_hitl_complete_takeover_click(editor: Locator) -> None:
    complete = editor.locator("section.wt-hitl .wt-hitl-complete button").first
    await expect(complete).to_be_visible(timeout=15_000)
    await worktracker_hitl_click_send_and_assert_http(editor.page, complete)


async def worktracker_hitl_assert_complete_hidden(editor: Locator) -> None:
    await expect(editor.locator("section.wt-hitl .wt-hitl-complete")).to_have_count(0)
    await expect(
        editor.locator("worktracker-detail-header worktracker-icon-action[icon='check']")
    ).to_have_count(0)
    await expect(
        editor.locator("worktracker-detail-inspector worktracker-icon-action[icon='check']")
    ).to_have_count(0)


async def worktracker_hitl_assert_chat_height(editor: Locator) -> None:
    chat = await worktracker_hitl_embedded_chat(editor)
    box = await chat.bounding_box()
    if box is None:
        raise AssertionError("HITL embedded chat has no bounding box")
    if box["height"] <= 0:
        raise AssertionError(f"HITL embedded chat height must be > 0, got {box['height']}")


async def worktracker_hitl_attach_file(editor: Locator, file_path: str) -> None:
    chat = await worktracker_hitl_embedded_chat(editor)
    file_input = chat.locator("input[type='file']").first
    await expect(file_input).to_be_attached(timeout=15_000)
    await file_input.set_input_files(file_path)
    await expect(chat.locator(".composer-file-chip").first).to_be_visible(timeout=30_000)


async def worktracker_inbox_open_panel(
    page: Page,
    worktracker_ui: AppUI,
    work_item_id: str,
) -> Locator:
    await worktracker_open_inbox(page, worktracker_ui)
    badge = page.locator(f"platform-work-item-badge[work-item-id='{work_item_id}']").first
    await expect(badge).to_be_visible(timeout=60_000)
    card = page.locator("worktracker-work-item-card").filter(has=badge).first
    await card.locator(".body").first.click()
    panel = page.locator(
        f"work-item-detail-panel[panel-open][work-item-id='{work_item_id}']"
    ).first
    await expect(panel).to_be_visible(timeout=30_000)
    editor = panel.locator("work-item-detail-editor").first
    await expect(editor).to_be_visible(timeout=30_000)
    return editor


async def worktracker_api_complete_work_item_response(
    origin: str,
    auth_token: str,
    work_item_id: str,
    *,
    resolution_text: str = "",
) -> httpx.Response:
    async with _worktracker_client(origin, auth_token) as client:
        return await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/complete",
            json={"resolution_text": resolution_text},
        )


async def crm_open_work_item_page(
    page: Page,
    crm_ui: AppUI,
    work_item_id: str,
) -> Locator:
    await page.goto(
        f"{crm_ui.origin}/crm/tasks/{work_item_id}",
        wait_until="domcontentloaded",
    )
    await expect(page.locator("crm-app")).to_be_visible(timeout=30_000)
    detail = page.locator(f"platform-work-item-detail[work-item-id='{work_item_id}']").first
    await expect(detail).to_be_visible(timeout=30_000)
    return detail


async def flows_user_chat_wait_text(page: Page, text_pattern: re.Pattern[str] | str) -> None:
    """Текст в чате покупателя (flows chat-page) — в т.ч. ответ оператора по Emitter."""
    chat = page.locator("chat-page").first
    await expect(chat).to_be_visible(timeout=30_000)
    pattern = (
        text_pattern
        if isinstance(text_pattern, re.Pattern)
        else re.compile(re.escape(text_pattern), re.I)
    )
    await expect(chat.get_by_text(pattern).first).to_be_visible(timeout=120_000)

"""Хелперы для сгенерированных UI-сценариев Worktracker (операторы, HITL)."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from playwright.async_api import Locator, Page, expect

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
    api_origin = worktracker_api_origin(origin)
    return httpx.AsyncClient(
        base_url=api_origin,
        cookies={"auth_token": auth_token},
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
    claim = editor.locator("worktracker-icon-action[icon='user-plus']").first
    await expect(claim).to_be_visible(timeout=15_000)
    await claim.click()


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

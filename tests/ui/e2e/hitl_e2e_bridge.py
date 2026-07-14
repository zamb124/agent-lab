"""Сквозной мост flows chat ↔ worktracker для HITL E2E сценариев."""

from __future__ import annotations

import asyncio
import re
import time

from urllib.parse import quote

from playwright.async_api import Page, expect

from apps.flows.src.services.hitl_demo_queue import EXAMPLE_HITL_SLUG
from core.types import JsonObject
from tests.ui.e2e.flows_e2e_helpers import (
    flows_chat_send_message,
    flows_open_chat_page,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    WORKTRACKER_API_PREFIX,
    worktracker_api_get_work_item,
    worktracker_api_list_work_items,
    worktracker_api_origin,
)
from tests.ui.harness import AppUI

FLOWS_TASKS_STATE_PATH = "/flows/api/v1/tasks/state"

EXAMPLE_REACT_ID = "example_react"
EXAMPLE_GRAPH_ID = "example_graph"
HITL_BRANCH_NODE = "hitl_operator_node"
HITL_BRANCH_REACT = "hitl_operator_react"
HITL_NODE_PAUSE = "hitl_pause"
HITL_REACT_NODE = "hitl_tool_main"
GREEN_GARDEN_HITL_MESSAGE = "Спорный возврат без чека — нужен оператор"
GREEN_GARDEN_OPERATOR_REPLY = (
    "Марина из поддержки «Зелёного сада»: оформим возврат по фото товара."
)
GREEN_GARDEN_TAKEOVER_MESSAGE = "Нужен перехват диалога по спорному возврату"


def hitl_worktracker_api_origin(origin: str) -> str:
    """Worktracker API живёт на отдельном порту test stack (9021)."""
    return worktracker_api_origin(origin)


async def hitl_ensure_demo_queue_member(origin: str, auth_token: str, user_id: str) -> str:
    import httpx

    api_origin = hitl_worktracker_api_origin(origin)
    async with httpx.AsyncClient(
        base_url=api_origin,
        cookies={"auth_token": auth_token},
        timeout=630.0,
    ) as client:
        queues_resp = await client.get(f"{WORKTRACKER_API_PREFIX}/work-queues")
        queues_resp.raise_for_status()
        items = queues_resp.json().get("items") or []
        queue_id = ""
        for item in items:
            if item.get("work_queue_slug") == EXAMPLE_HITL_SLUG:
                queue_id = str(item["work_queue_id"])
                break
        if not queue_id:
            create_resp = await client.post(
                f"{WORKTRACKER_API_PREFIX}/work-queues",
                json={"name": "Demo HITL", "slug": EXAMPLE_HITL_SLUG},
            )
            create_resp.raise_for_status()
            queue_id = str(create_resp.json()["work_queue_id"])
        member_resp = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-queues/{queue_id}/members",
            json={"member": {"actor_kind": "user", "user_id": user_id}, "role": "member"},
        )
        if member_resp.status_code >= 400 and member_resp.status_code != 409:
            member_resp.raise_for_status()
        return queue_id


async def hitl_open_react_branch_chat(
    page: Page,
    flows_ui: AppUI,
    branch_id: str = HITL_BRANCH_NODE,
) -> None:
    await flows_open_chat_page(page, flows_ui, EXAMPLE_REACT_ID, branch_id=branch_id)


async def hitl_trigger_deterministic(page: Page, message: str = "Нужен оператор") -> str:
    await flows_chat_send_message(page, message)
    return await hitl_wait_chat_input_required(page)


async def hitl_api_wait_conversation_text(
    flows_origin: str,
    auth_token: str,
    work_item_id: str,
    text_pattern: re.Pattern[str] | str,
    *,
    timeout_s: float = 120.0,
) -> None:
    """Ждёт текст в GET /flows/api/v1/hitl/{work_item_id}/conversation (снимок леджера)."""
    import httpx

    pattern = (
        text_pattern
        if isinstance(text_pattern, re.Pattern)
        else re.compile(re.escape(text_pattern), re.I)
    )
    deadline = time.monotonic() + timeout_s
    path = f"/flows/api/v1/hitl/{work_item_id}/conversation"
    last_turns: list[str] | None = None
    last_policy: object = None
    session_debug: dict[str, object] | None = None
    async with httpx.AsyncClient(
        base_url=flows_origin,
        cookies={"auth_token": auth_token},
        timeout=630.0,
    ) as client:
        while time.monotonic() < deadline:
            response = await client.get(path)
            if response.status_code < 400:
                payload = response.json()
                last_policy = payload.get("policy")
                turns = payload.get("turns")
                if isinstance(turns, list):
                    last_turns = [
                        str(turn.get("text"))
                        for turn in turns
                        if isinstance(turn, dict) and isinstance(turn.get("text"), str)
                    ]
                    for turn in turns:
                        if isinstance(turn, dict):
                            text = turn.get("text")
                            if isinstance(text, str) and pattern.search(text):
                                return
            if (
                session_debug is None
                and isinstance(last_policy, dict)
                and isinstance(last_policy.get("conversation"), dict)
            ):
                session_id = last_policy["conversation"].get("session_id")
                if isinstance(session_id, str) and session_id:
                    state_resp = await client.get(
                        FLOWS_TASKS_STATE_PATH,
                        params={"session_id": session_id},
                    )
                    if state_resp.status_code < 400:
                        state_payload = state_resp.json()
                        if isinstance(state_payload, dict):
                            session_debug = {
                                "content": state_payload.get("content"),
                                "message_count": len(state_payload.get("messages") or [])
                                if isinstance(state_payload.get("messages"), list)
                                else None,
                            }
            await asyncio.sleep(1.0)
    raise AssertionError(
        f"conversation {work_item_id!r} did not contain {pattern.pattern!r} within {timeout_s}s"
        + (f"; last turns={last_turns!r}" if last_turns is not None else "")
        + (f"; policy={last_policy!r}" if last_policy is not None else "")
        + (f"; session_debug={session_debug!r}" if session_debug is not None else "")
    )


async def hitl_wait_chat_input_required(page: Page) -> str:
    banner = page.locator("chat-page .input-required-banner").first
    await expect(banner).to_be_visible(timeout=120_000)
    badge = page.locator("chat-page platform-work-item-badge[work-item-id]").first
    await expect(badge).to_be_visible(timeout=30_000)
    work_item_id = await badge.get_attribute("work-item-id")
    if not work_item_id:
        raise AssertionError("platform-work-item-badge must expose work-item-id")
    return work_item_id


def _work_item_session_id(item: JsonObject) -> str:
    links = item.get("links")
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict):
                session_id = link.get("session_id")
                if isinstance(session_id, str) and session_id:
                    return session_id
    hooks = item.get("hooks")
    if isinstance(hooks, list):
        for hook in hooks:
            if isinstance(hook, dict):
                binding = hook.get("binding")
                if isinstance(binding, dict):
                    session_id = binding.get("session_id")
                    if isinstance(session_id, str) and session_id:
                        return session_id
    raise AssertionError("work item links/hooks must contain session_id")


async def hitl_wait_work_item_terminal(
    origin: str,
    auth_token: str,
    work_item_id: str,
    *,
    timeout_s: float = 120.0,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        item = await worktracker_api_get_work_item(origin, auth_token, work_item_id)
        state = str(item.get("state") or "")
        if state in {"done", "cancelled"}:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"work item {work_item_id!r} did not reach terminal state within {timeout_s}s"
    )


def _message_texts_from_session_state(state: JsonObject) -> list[str]:
    messages = state.get("messages")
    if not isinstance(messages, list):
        return []
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        parts = message.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        texts.append(text)
        content = message.get("content")
        if isinstance(content, str) and content:
            texts.append(content)
    return texts


async def hitl_wait_session_contains(
    flows_origin: str,
    auth_token: str,
    session_id: str,
    *,
    text_pattern: re.Pattern[str] | str,
    timeout_s: float = 120.0,
) -> None:
    import httpx

    pattern = (
        text_pattern
        if isinstance(text_pattern, re.Pattern)
        else re.compile(re.escape(text_pattern), re.I)
    )
    deadline = time.monotonic() + timeout_s
    async with httpx.AsyncClient(
        base_url=flows_origin,
        cookies={"auth_token": auth_token},
        timeout=630.0,
    ) as client:
        while time.monotonic() < deadline:
            response = await client.get(
                FLOWS_TASKS_STATE_PATH,
                params={"session_id": session_id},
            )
            if response.status_code < 400:
                state = response.json()
                if isinstance(state, dict):
                    for text in _message_texts_from_session_state(state):
                        if pattern.search(text):
                            return
            await asyncio.sleep(1.0)
    raise AssertionError(
        f"session {session_id!r} did not contain {pattern.pattern!r} within {timeout_s}s"
    )


async def hitl_session_chat_url(
    origin: str,
    auth_token: str,
    work_item_id: str,
    flows_ui: AppUI,
    flow_id: str,
) -> str:
    item = await worktracker_api_get_work_item(origin, auth_token, work_item_id)
    session_id = _work_item_session_id(item)
    encoded = quote(session_id, safe="")
    return f"{flows_ui.origin}/flows/{flow_id}/session/{encoded}"


async def hitl_return_to_chat_session(
    page: Page,
    *,
    origin: str,
    auth_token: str,
    work_item_id: str,
    flows_ui: AppUI,
    flow_id: str,
    expect_operator_text: str | None = None,
) -> None:
    item = await worktracker_api_get_work_item(origin, auth_token, work_item_id)
    session_id = _work_item_session_id(item)
    if expect_operator_text:
        await hitl_wait_work_item_terminal(origin, auth_token, work_item_id)
        if "Марина" in expect_operator_text:
            session_pattern: re.Pattern[str] | str = re.compile(
                r"Марина|Marina|поддержк", re.I
            )
        else:
            session_pattern = expect_operator_text[:48].strip()
        await hitl_wait_session_contains(
            flows_ui.origin,
            auth_token,
            session_id,
            text_pattern=session_pattern,
        )
    session_url = await hitl_session_chat_url(
        origin,
        auth_token,
        work_item_id,
        flows_ui,
        flow_id,
    )
    await page.goto(session_url, wait_until="domcontentloaded")
    await expect(page.locator("chat-page")).to_be_visible(timeout=30_000)
    await hitl_wait_chat_resume(page, expect_operator_text=expect_operator_text)


async def hitl_operator_claim_and_complete(
    origin: str,
    auth_token: str,
    work_item_id: str,
    resolution_text: str,
) -> None:
    import httpx

    api_origin = hitl_worktracker_api_origin(origin)
    async with httpx.AsyncClient(
        base_url=api_origin,
        cookies={"auth_token": auth_token},
        timeout=630.0,
    ) as client:
        claim_resp = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/claim",
            json={},
        )
        if claim_resp.status_code >= 400:
            raise AssertionError(
                f"claim failed: {claim_resp.status_code} {claim_resp.text}"
            )
        complete_resp = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/complete",
            json={"resolution_text": resolution_text},
        )
        if complete_resp.status_code >= 400:
            raise AssertionError(
                f"complete failed: {complete_resp.status_code} {complete_resp.text}"
            )


async def hitl_wait_chat_resume(page: Page, *, expect_operator_text: str | None = None) -> None:
    await expect(page.locator("chat-page .input-required-banner")).to_be_hidden(timeout=120_000)
    if expect_operator_text:
        chat = page.locator("chat-page").first
        if "Марина" in expect_operator_text:
            reply = chat.get_by_text(re.compile(r"Марина|Marina|поддержк", re.I)).first
        else:
            snippet = expect_operator_text[:48].strip()
            reply = chat.get_by_text(re.compile(re.escape(snippet))).first
        await expect(reply).to_be_visible(timeout=120_000)


async def hitl_find_latest_queue_task(
    origin: str,
    auth_token: str,
    *,
    work_queue_slug: str = EXAMPLE_HITL_SLUG,
) -> JsonObject:
    items = await worktracker_api_list_work_items(
        origin,
        auth_token,
        queue_unclaimed_only="true",
        exclude_terminal="true",
    )
    for item in items:
        assignment = item.get("assignment")
        if not isinstance(assignment, dict):
            continue
        if assignment.get("work_queue_id") or assignment.get("assignee_kind") == "queue":
            return item
    raise AssertionError(f"No unclaimed queue task found for slug {work_queue_slug!r}")


async def hitl_assert_work_item_terminal(origin: str, auth_token: str, work_item_id: str) -> None:
    item = await worktracker_api_get_work_item(origin, auth_token, work_item_id)
    state = str(item.get("state") or "")
    if state not in {"done", "cancelled"}:
        raise AssertionError(f"Expected terminal work item, got state={state!r}")

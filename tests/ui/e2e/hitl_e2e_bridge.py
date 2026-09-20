"""Сквозной мост flows chat ↔ worktracker для HITL E2E сценариев."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import quote

import httpx
from playwright.async_api import Locator, Page, expect

from apps.flows.src.services.hitl_demo_queue import EXAMPLE_HITL_SLUG
from core.flow_ui.document import (
    FlowUIActionSpec,
    FlowUIButton,
    FlowUIDocument,
    FlowUIMarkdownText,
    FlowUIPage,
    FlowUITextInput,
)
from core.types import JsonObject
from tests.flows._a2a_v1 import A2A_HEADERS, a2a_send_message
from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_chat_send_message,
    flows_open_chat_page,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    WORKTRACKER_API_PREFIX,
    worktracker_api_get_work_item,
    worktracker_api_list_work_items,
    worktracker_api_origin,
    worktracker_wait_queue_task_id,
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


def _queue_member_user_id(row: object) -> str:
    if not isinstance(row, dict):
        raise AssertionError(f"queue member row must be an object, got {type(row)}")
    member = row.get("member")
    if not isinstance(member, dict):
        raise AssertionError("queue member.member must be an object")
    member_user_id = member.get("user_id")
    if not isinstance(member_user_id, str) or member_user_id == "":
        raise AssertionError("queue member.member.user_id must be a non-empty string")
    return member_user_id


async def _ensure_queue_member(client: httpx.AsyncClient, queue_id: str, user_id: str) -> None:
    add_resp = await client.post(
        f"{WORKTRACKER_API_PREFIX}/work-queues/{queue_id}/members",
        json={
            "member": {"actor_kind": "user", "user_id": user_id},
            "role": "member",
        },
    )
    if add_resp.status_code not in {200, 201, 409, 403}:
        add_resp.raise_for_status()
    members_resp = await client.get(f"{WORKTRACKER_API_PREFIX}/work-queues/{queue_id}/members")
    members_resp.raise_for_status()
    payload = members_resp.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise AssertionError(f"queue members must be {{items: list}}, got {payload!r}")
    members = payload["items"]
    for row in members:
        if _queue_member_user_id(row) == user_id:
            return
    raise AssertionError(
        f"{user_id} is not a member of queue {queue_id} "
        f"(add_status={add_resp.status_code} add_body={add_resp.text})"
    )


async def hitl_ensure_demo_queue_member(origin: str, auth_token: str, user_id: str) -> str:
    from tests.ui.e2e_worker import ui_e2e_scope_headers

    api_origin = hitl_worktracker_api_origin(origin)
    async with httpx.AsyncClient(
        base_url=api_origin,
        cookies={"auth_token": auth_token},
        headers=ui_e2e_scope_headers(),
        timeout=630.0,
    ) as client:
        queues_resp = await client.get(f"{WORKTRACKER_API_PREFIX}/work-queues")
        queues_resp.raise_for_status()
        payload = queues_resp.json()
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise AssertionError("work-queues list must contain items[]")
        queue_id = ""
        for item in items:
            if not isinstance(item, dict):
                raise AssertionError("work-queue row must be an object")
            if item.get("work_queue_slug") == EXAMPLE_HITL_SLUG:
                queue_id = str(item["work_queue_id"])
                break
        if not queue_id:
            create_resp = await client.post(
                f"{WORKTRACKER_API_PREFIX}/work-queues",
                json={"name": "Demo HITL", "slug": EXAMPLE_HITL_SLUG},
            )
            if create_resp.status_code == 409:
                queues_resp = await client.get(f"{WORKTRACKER_API_PREFIX}/work-queues")
                queues_resp.raise_for_status()
                payload = queues_resp.json()
                items = payload.get("items") if isinstance(payload, dict) else None
                if not isinstance(items, list):
                    raise AssertionError("work-queues list must contain items[]")
                for item in items:
                    if not isinstance(item, dict):
                        raise AssertionError("work-queue row must be an object")
                    if item.get("work_queue_slug") == EXAMPLE_HITL_SLUG:
                        queue_id = str(item["work_queue_id"])
                        break
                if not queue_id:
                    raise AssertionError(
                        f"example_hitl exists but is not visible to {user_id}"
                    )
            else:
                create_resp.raise_for_status()
                created = create_resp.json()
                if not isinstance(created, dict):
                    raise AssertionError("create work-queue must return an object")
                queue_id = str(created["work_queue_id"])
        await _ensure_queue_member(client, queue_id, user_id)
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


async def hitl_api_assert_turn_role(
    flows_origin: str,
    auth_token: str,
    work_item_id: str,
    text: str,
    role: str,
    *,
    timeout_s: float = 60.0,
) -> None:
    import httpx

    deadline = time.monotonic() + timeout_s
    path = f"/flows/api/v1/hitl/{work_item_id}/conversation"
    last_turns: object | None = None
    last_status: int | None = None
    async with httpx.AsyncClient(
        base_url=flows_origin,
        cookies={"auth_token": auth_token},
        timeout=30.0,
    ) as client:
        while time.monotonic() < deadline:
            response = await client.get(path)
            last_status = response.status_code
            if response.status_code < 400:
                payload = response.json()
                turns = payload.get("turns")
                last_turns = turns
                if isinstance(turns, list):
                    for turn in turns:
                        if (
                            isinstance(turn, dict)
                            and turn.get("text") == text
                            and turn.get("role") == role
                        ):
                            return
            await asyncio.sleep(0.5)
    raise AssertionError(
        f"conversation {work_item_id!r} has no turn text={text!r} role={role!r}"
        f"; status={last_status!r} last={last_turns!r}"
    )


async def hitl_wait_chat_input_required(page: Page) -> str:
    return await hitl_wait_host_input_required(hitl_user_flow_ui(page, surface="spa"))


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

    from tests.ui.e2e_worker import ui_e2e_scope_headers

    api_origin = hitl_worktracker_api_origin(origin)
    async with httpx.AsyncClient(
        base_url=api_origin,
        cookies={"auth_token": auth_token},
        headers=ui_e2e_scope_headers(),
        timeout=630.0,
    ) as client:
        claim_resp = await client.post(
            f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/claim",
            json={},
        )
        if claim_resp.status_code >= 400 and claim_resp.status_code != 409:
            raise AssertionError(
                f"claim failed: {claim_resp.status_code} {claim_resp.text}"
            )
        last_detail = ""
        for attempt in range(5):
            complete_resp = await client.post(
                f"{WORKTRACKER_API_PREFIX}/work-items/{work_item_id}/complete",
                json={"resolution_text": resolution_text},
            )
            if complete_resp.status_code < 400:
                return
            last_detail = complete_resp.text
            try:
                last_detail = str(complete_resp.json())
            except ValueError:
                pass
            # 409/500 сразу после claim — hooks/resume ещё не готовы.
            if complete_resp.status_code not in {409, 500} or attempt == 4:
                break
            await asyncio.sleep(0.4 * (attempt + 1))
        raise AssertionError(
            f"complete failed: {complete_resp.status_code} {last_detail}"
        )


async def hitl_wait_chat_resume(page: Page, *, expect_operator_text: str | None = None) -> None:
    await expect(page.locator("chat-page .input-required-banner")).to_be_hidden(timeout=90_000)
    if expect_operator_text:
        chat = page.locator("chat-page").first
        if "Марина" in expect_operator_text:
            reply = chat.get_by_text(re.compile(r"Марина|Marina|поддержк", re.I)).first
        else:
            snippet = expect_operator_text[:48].strip()
            reply = chat.get_by_text(re.compile(re.escape(snippet))).first
        await expect(reply).to_be_visible(timeout=45_000)


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


async def hitl_assert_work_item_open(origin: str, auth_token: str, work_item_id: str) -> None:
    item = await worktracker_api_get_work_item(origin, auth_token, work_item_id)
    state = str(item.get("state") or "")
    if state in {"done", "cancelled", "failed"}:
        raise AssertionError(f"Expected open HITL work item, got state={state!r}")


def hitl_user_flow_ui(
    page: Page,
    *,
    surface: Literal["spa", "embed", "run"],
) -> Locator:
    if surface == "spa":
        return page.locator("chat-page platform-flow-ui").first
    if surface == "embed":
        return page.locator(
            "flow-ui-drawer platform-flow-ui, flow-ui-page-host platform-flow-ui, platform-flow-ui"
        ).first
    if surface == "run":
        return page.locator("flows-execution-panel platform-flow-ui").first
    raise ValueError(f"unknown HITL user surface: {surface!r}")


async def hitl_wait_host_input_required(host: Locator) -> str:
    banner = host.locator(".input-required-banner").first
    await expect(banner).to_be_visible(timeout=90_000)
    badge = host.locator("platform-work-item-badge[work-item-id]").first
    await expect(badge).to_be_attached(timeout=30_000)
    work_item_id = await badge.get_attribute("work-item-id")
    if not work_item_id:
        raise AssertionError("platform-work-item-badge must expose work-item-id")
    return work_item_id


HITL_COMPOSER_SELECTOR = 'textarea[data-canon="composer"]'


async def hitl_assert_composer_readonly(host: Locator) -> None:
    """Пользователь ждёт оператора (single_reply): composer на месте, но только для чтения."""
    textarea = host.locator(HITL_COMPOSER_SELECTOR).first
    await expect(textarea).to_be_visible(timeout=30_000)
    await expect(textarea).not_to_be_editable(timeout=20_000)


async def hitl_assert_composer_absent(host: Locator) -> None:
    """Без права хода (нет доступа к очереди, задача закрыта) composer не рендерится."""
    await expect(host.locator("flow-ui-page")).to_be_visible(timeout=30_000)
    await expect(host.locator(HITL_COMPOSER_SELECTOR)).to_have_count(0, timeout=30_000)


async def hitl_assert_composer_editable(host: Locator) -> None:
    textarea = host.locator(HITL_COMPOSER_SELECTOR).first
    await expect(textarea).to_be_visible(timeout=30_000)
    await expect(textarea).to_be_editable(timeout=20_000)


async def hitl_host_send(host: Locator, text: str) -> None:
    textarea = host.locator(HITL_COMPOSER_SELECTOR).first
    await expect(textarea).to_be_visible(timeout=30_000)
    await textarea.fill(text)
    send_btn = host.get_by_role(
        "button",
        name=re.compile(
            r"Ответить и завершить|Reply and complete|Отправить|Send|Submit"
        ),
    ).first
    await expect(send_btn).to_be_enabled(timeout=10_000)
    await send_btn.click()


async def hitl_host_attach_files(host: Locator, file_path: str) -> None:
    file_input = host.locator("input[type='file']").first
    await expect(file_input).to_be_attached(timeout=15_000)
    await file_input.set_input_files(file_path)


async def hitl_api_get_conversation(
    flows_origin: str,
    auth_token: str,
    work_item_id: str,
) -> JsonObject:
    import httpx

    path = f"/flows/api/v1/hitl/{work_item_id}/conversation"
    async with httpx.AsyncClient(
        base_url=flows_origin,
        cookies={"auth_token": auth_token},
        timeout=30.0,
    ) as client:
        response = await client.get(path)
    if response.status_code >= 400:
        raise AssertionError(
            f"GET conversation failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("GET conversation must return an object")
    return payload


async def hitl_api_assert_conversation_lacks_text(
    flows_origin: str,
    auth_token: str,
    work_item_id: str,
    text: str,
) -> None:
    payload = await hitl_api_get_conversation(flows_origin, auth_token, work_item_id)
    turns = payload.get("turns")
    if not isinstance(turns, list):
        raise AssertionError("conversation turns must be a list")
    for turn in turns:
        if isinstance(turn, dict) and turn.get("text") == text:
            raise AssertionError(
                f"conversation {work_item_id!r} unexpectedly contains {text!r}"
            )


async def hitl_api_assert_turn_has_files(
    flows_origin: str,
    auth_token: str,
    work_item_id: str,
    text: str,
    *,
    timeout_s: float = 60.0,
) -> None:
    import httpx

    deadline = time.monotonic() + timeout_s
    path = f"/flows/api/v1/hitl/{work_item_id}/conversation"
    last_turns: object = None
    async with httpx.AsyncClient(
        base_url=flows_origin,
        cookies={"auth_token": auth_token},
        timeout=30.0,
    ) as client:
        while time.monotonic() < deadline:
            response = await client.get(path)
            if response.status_code < 400:
                payload = response.json()
                turns = payload.get("turns")
                last_turns = turns
                if isinstance(turns, list):
                    for turn in turns:
                        if not isinstance(turn, dict):
                            continue
                        if turn.get("text") != text:
                            continue
                        file_ids = turn.get("file_ids")
                        if isinstance(file_ids, list) and len(file_ids) > 0:
                            return
            await asyncio.sleep(0.5)
    raise AssertionError(
        f"conversation {work_item_id!r} has no file_ids on turn {text!r}; last={last_turns!r}"
    )


def _interface_dump(document: FlowUIDocument) -> JsonObject:
    dumped = document.model_dump(mode="json")
    if not isinstance(dumped, dict):
        raise RuntimeError("FlowUIDocument dump must be an object")
    return dumped


def hitl_host_composer_interface_config() -> JsonObject:
    """Interface без conversation: оператор видит host-composer."""
    return _interface_dump(
        FlowUIDocument(
            start_page_id="main",
            pages=[
                FlowUIPage(
                    page_id="main",
                    title="HITL",
                    blocks=[
                        FlowUIMarkdownText(block_id="note", markdown="Operator form"),
                        FlowUIButton(
                            block_id="submit",
                            label="Send",
                            action=FlowUIActionSpec(name="submit"),
                        ),
                    ],
                )
            ],
        )
    )


def hitl_form_submit_interface_config() -> JsonObject:
    """Кастомная форма с Submit без conversation."""
    return _interface_dump(
        FlowUIDocument(
            start_page_id="main",
            pages=[
                FlowUIPage(
                    page_id="main",
                    title="HITL form",
                    blocks=[
                        FlowUITextInput(block_id="note-field", field="message", label="Reply"),
                        FlowUIButton(
                            block_id="submit",
                            label="Send",
                            action=FlowUIActionSpec(name="submit"),
                        ),
                    ],
                )
            ],
        )
    )


def hitl_custom_ui_flow_payload(
    *,
    flow_id: str,
    queue_slug: str,
    mode: str,
    interface: JsonObject,
    title: str,
) -> JsonObject:
    return {
        "flow_id": flow_id,
        "name": flow_id,
        "entry": "hitl",
        "nodes": {
            "hitl": {
                "type": "hitl_node",
                "work_queue_slug": queue_slug,
                "handoff_task_title": title,
                "handoff_user_message": "Ожидается оператор",
                "handoff_mode": mode,
            }
        },
        "edges": [{"from_node": "hitl", "to_node": None}],
        "interface": interface,
    }


async def hitl_create_custom_ui_flow(
    origin: str,
    auth_token: str,
    *,
    flow_id: str,
    mode: str,
    interface: JsonObject,
    title: str,
    queue_slug: str = EXAMPLE_HITL_SLUG,
) -> None:
    await flows_api_create_flow(
        origin,
        auth_token,
        hitl_custom_ui_flow_payload(
            flow_id=flow_id,
            queue_slug=queue_slug,
            mode=mode,
            interface=interface,
            title=title,
        ),
    )


def hitl_chat_hitl_flow_payload(
    *,
    flow_id: str,
    queue_slug: str,
    mode: str,
    title: str,
) -> JsonObject:
    return {
        "flow_id": flow_id,
        "name": flow_id,
        "entry": "hitl",
        "nodes": {
            "hitl": {
                "type": "hitl_node",
                "work_queue_slug": queue_slug,
                "handoff_task_title": title,
                "handoff_user_message": "Ожидается оператор",
                "handoff_mode": mode,
            }
        },
        "edges": [{"from_node": "hitl", "to_node": None}],
    }


async def hitl_create_chat_hitl_flow(
    origin: str,
    auth_token: str,
    *,
    flow_id: str,
    mode: str,
    title: str,
    queue_slug: str = EXAMPLE_HITL_SLUG,
) -> None:
    await flows_api_create_flow(
        origin,
        auth_token,
        hitl_chat_hitl_flow_payload(
            flow_id=flow_id,
            queue_slug=queue_slug,
            mode=mode,
            title=title,
        ),
    )


async def hitl_start_via_a2a(
    origin: str,
    auth_token: str,
    *,
    flow_id: str,
    text: str,
    title_contains: str,
) -> str:
    import httpx

    from tests.ui.e2e_worker import ui_e2e_scope_headers

    async with httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        headers={**ui_e2e_scope_headers(), **A2A_HEADERS},
        timeout=630.0,
    ) as client:
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=a2a_send_message(text),
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"A2A SendMessage failed: {response.status_code} {response.text}"
        )
    body = response.json()
    if isinstance(body, dict) and body.get("error") is not None:
        raise AssertionError(f"A2A SendMessage error: {body}")
    return await worktracker_wait_queue_task_id(
        origin,
        auth_token,
        title_contains=title_contains,
        timeout_s=120.0,
    )


@asynccontextmanager
async def hitl_embed_opened(
    page: Page,
    *,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    auth_headers: dict[str, str],
    company_id: str,
    unique_id: str,
    flow_id: str = EXAMPLE_GRAPH_ID,
) -> AsyncIterator[Locator]:
    from httpx import AsyncClient

    from tests.ui.e2e.test_embed_autoload_browser import (
        _build_embed_page_html,
        _create_embed_config,
        _delete_embed_config,
        _external_embed_origin,
        _flows_api_origin,
        _frontend_api_origin,
    )

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"
    embed_id: str | None = None
    errors: list[str] = []
    network_events: list[str] = []
    try:
        async with AsyncClient(
            base_url=frontend_origin,
            follow_redirects=True,
            timeout=20.0,
        ) as fc:
            embed_id = await _create_embed_config(
                frontend_origin,
                auth_headers,
                flow_id=flow_id,
                unique_id=unique_id,
                show_launcher=True,
            )
            mint = await fc.post(
                f"/frontend/api/embed/configs/{embed_id}/session-token",
                headers=auth_headers,
                json={"expires_in_seconds": 300},
            )
            if mint.status_code >= 400:
                raise AssertionError(
                    f"embed session-token failed: {mint.status_code} {mint.text}"
                )
            token_payload = {"token": mint.json()["token"]}
        page_html = _build_embed_page_html(
            script_src=script_src,
            embed_id=embed_id,
            flows_base=flows_base,
            frontend_origin=frontend_origin,
            company_id=company_id,
            show_launcher=True,
        )
        with _external_embed_origin(
            html_page_utf8=page_html,
            token_payload=token_payload,
        ) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded")
            try:
                await page.wait_for_function(
                    "typeof window.linnexFlowUI !== 'undefined' && window.linnexFlowUI && window.linnexFlowUI.element",
                    timeout=60_000,
                )
                await page.locator("flow-ui-drawer, flow-ui-page-host").first.wait_for(
                    state="attached",
                    timeout=30_000,
                )
            except Exception as exc:
                raise AssertionError(
                    "linnexFlowUI не смонтировался для HITL embed\n"
                    f"errors:\n{chr(10).join(errors) or '<empty>'}\n\n"
                    f"network:\n{chr(10).join(network_events) or '<empty>'}"
                ) from exc
            fab = page.locator("flow-ui-drawer").locator("button.launcher, button.fab").first
            await expect(fab).to_be_visible(timeout=15_000)
            await fab.click()
            host = hitl_user_flow_ui(page, surface="embed")
            await expect(host).to_be_visible(timeout=30_000)
            yield host
    finally:
        if embed_id is not None:
            await _delete_embed_config(frontend_origin, auth_headers, embed_id)

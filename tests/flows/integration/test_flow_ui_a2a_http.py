"""Flow UI поверх чистого A2A: ui-action ход, проекция state в артефакт, resume через ui-action."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from apps.flows.src.container import get_container
from core.context import require_context
from core.flow_ui.document import FlowUIDocument
from core.state import ExecutionState
from tests.flows._a2a_v1 import A2A_HEADERS
from tests.flows._flow_ui_session import (
    a2a_get_task,
    a2a_send,
    a2a_send_error,
    ensure_flow,
    state_from_task,
    status_text,
    text_message,
    text_of,
    ui_action_message,
)
from tests.flows.a2a_conformance.helpers.flows import delete_flow

ECHO_FIELDS_CODE = (
    "async def run(args, state):\n"
    "    state['response'] = f\"ECHO:{state.get('content') or ''}\"\n"
    "    state['greeting'] = f\"Hi, {state.get('name') or 'stranger'}\"\n"
    "    return state\n"
)


def _lead_form_interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "pages": [
                {
                    "page_id": "main",
                    "title": "Lead",
                    "blocks": [
                        {
                            "type": "text_input",
                            "block_id": "name-input",
                            "field": "name",
                            "label": "Имя",
                            "required": True,
                        },
                        {
                            "type": "text_input",
                            "block_id": "email-input",
                            "field": "email",
                            "label": "Email",
                        },
                        {
                            "type": "button",
                            "block_id": "send",
                            "label": "Отправить",
                            "action": {"name": "submit"},
                        },
                        {"type": "text", "block_id": "greeting", "markdown": "{greeting}"},
                        {"type": "conversation", "block_id": "conversation"},
                    ],
                }
            ],
            "start_page_id": "main",
        }
    )


async def _wait_state_response(session_id: str, *, needle: str) -> ExecutionState:
    for _ in range(80):
        state = await get_container().workflow_runtime.get_state(session_id)
        if state is not None and state.response and needle in str(state.response):
            return state
        await asyncio.sleep(0.25)
    state = await get_container().workflow_runtime.get_state(session_id)
    raise AssertionError(f"response {needle!r} missing for {session_id}; state={state!r}")


@pytest.mark.asyncio
async def test_ui_action_fields_become_state_and_state_artifact_follows_interface(
    client: AsyncClient,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    _ = require_context()
    flow_id = f"a2a_flow_ui_{unique_id}"
    context_id = f"ctx-a2a-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    _ = await ensure_flow(flow_id=flow_id, interface=_lead_form_interface(), code=ECHO_FIELDS_CODE)
    try:
        task = await a2a_send(
            client,
            flow_id=flow_id,
            message=ui_action_message(
                context_id=context_id,
                action="submit",
                source="send",
                fields={"name": f"Ann-{unique_id}", "email": "ann@example.com"},
            ),
        )
        assert task["contextId"] == context_id
        assert task["status"]["state"] == "TASK_STATE_COMPLETED", task

        state = await _wait_state_response(session_id, needle="ECHO:")
        assert state.name == f"Ann-{unique_id}"  # pyright: ignore[reportAttributeAccessIssue]
        assert state.email == "ann@example.com"  # pyright: ignore[reportAttributeAccessIssue]
        assert state.ui_action is not None
        assert state.ui_action.name == "submit"
        assert state.ui_action.source == "send"
        assert (
            state.content == f"Действие: submit\n- Имя: Ann-{unique_id}\n- Email: ann@example.com"
        )

        projected = state_from_task(task)
        # Артефакт state несёт только поля, на которые ссылается интерфейс.
        assert projected == {
            "name": f"Ann-{unique_id}",
            "email": "ann@example.com",
            "greeting": f"Hi, Ann-{unique_id}",
        }
        assert status_text(task) == f"ECHO:{state.content}"

        rehydrated = await a2a_get_task(client, flow_id=flow_id, task_id=str(task["id"]))
        assert state_from_task(rehydrated) == projected
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_ui_action_rejects_unknown_field_and_missing_required(
    client: AsyncClient,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    _ = require_context()
    flow_id = f"a2a_flow_ui_reject_{unique_id}"
    context_id = f"ctx-reject-{unique_id}"
    _ = await ensure_flow(flow_id=flow_id, interface=_lead_form_interface(), code=ECHO_FIELDS_CODE)
    try:
        unknown = await a2a_send_error(
            client,
            flow_id=flow_id,
            message=ui_action_message(
                context_id=context_id,
                action="submit",
                source="send",
                fields={"name": "Ann", "phone": "+7"},
            ),
        )
        assert "phone" in str(unknown), unknown

        missing_required = await a2a_send_error(
            client,
            flow_id=flow_id,
            message=ui_action_message(
                context_id=context_id, action="submit", source="send", fields={"email": "a@b.c"}
            ),
        )
        assert "required field 'name'" in str(missing_required), missing_required

        assert await get_container().workflow_runtime.get_state(f"{flow_id}:{context_id}") is None
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_text_turn_after_ui_action_keeps_fields_in_state(
    client: AsyncClient,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    _ = require_context()
    flow_id = f"a2a_flow_ui_text_{unique_id}"
    context_id = f"ctx-text-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    _ = await ensure_flow(flow_id=flow_id, interface=_lead_form_interface(), code=ECHO_FIELDS_CODE)
    try:
        _ = await a2a_send(
            client,
            flow_id=flow_id,
            message=ui_action_message(
                context_id=context_id, action="submit", source="send", fields={"name": "Ann"}
            ),
        )
        follow_up = await a2a_send(
            client,
            flow_id=flow_id,
            message=text_message(context_id=context_id, text=f"hello-{unique_id}"),
        )
        state = await _wait_state_response(session_id, needle=f"ECHO:hello-{unique_id}")
        assert state.name == "Ann"  # pyright: ignore[reportAttributeAccessIssue]
        assert state.ui_action is None
        assert state_from_task(follow_up)["name"] == "Ann"
    finally:
        await delete_flow(client, flow_id)


async def _create_ask_user_llm_flow(client: AsyncClient, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json={
            "flow_id": flow_id,
            "name": "Flow UI ask_user resume",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Use ask_user when you need a clarifying question.",
                    "tools": ["ask_user"],
                },
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "interface": _lead_form_interface().model_dump(mode="json"),
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_ui_action_resumes_ask_user_on_the_same_task(
    client: AsyncClient,
    app: object,
    unique_id: str,
    mock_llm_with_queue: object,
    sync_tools: object,
) -> None:
    """ask_user → INPUT_REQUIRED; ответ формой (ui-action) продолжает тот же A2A Task."""
    _ = app
    _ = sync_tools
    _ = require_context()
    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "What is your name?"}},
            "Hello, FlowUI!",
        ]
    )
    flow_id = f"a2a_flow_ui_ask_{unique_id}"
    context_id = f"ctx-ask-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    await _create_ask_user_llm_flow(client, flow_id)
    try:
        interrupted = await a2a_send(
            client, flow_id=flow_id, message=text_message(context_id=context_id, text="hi")
        )
        assert interrupted["status"]["state"] == "TASK_STATE_INPUT_REQUIRED", interrupted
        task_id = str(interrupted["id"])

        state_after_interrupt = await get_container().workflow_runtime.get_state(session_id)
        assert state_after_interrupt is not None
        assert state_after_interrupt.interrupt is not None
        assert state_after_interrupt.terminal_task_state == "input-required"

        resumed = await a2a_send(
            client,
            flow_id=flow_id,
            message=ui_action_message(
                context_id=context_id,
                action="submit",
                source="send",
                fields={"name": "FlowUI"},
                task_id=task_id,
            ),
        )
        assert resumed["id"] == task_id
        assert resumed["status"]["state"] == "TASK_STATE_COMPLETED", resumed
        assert "Hello, FlowUI!" in text_of(resumed, "response")

        state = await get_container().workflow_runtime.get_state(session_id)
        assert state is not None
        assert state.interrupt is None
        assert state.name == "FlowUI"  # pyright: ignore[reportAttributeAccessIssue]
        assert state_from_task(resumed)["name"] == "FlowUI"
    finally:
        await delete_flow(client, flow_id)

"""A2A HTTP bootstrap/sync for Flow UI without graph invocation."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient

from apps.flows.src.channels.a2a import _flow_ui_task_id
from apps.flows.src.container import get_container
from core.a2a import (
    PLATFORM_UI_BOOTSTRAP_ACTION,
    PLATFORM_UI_SUBMIT_ACTION,
    PLATFORM_UI_SYNC_ACTION,
)
from core.context import require_context
from tests.flows._a2a_v1 import A2A_HEADERS
from tests.flows._flow_ui_session import a2a_flow_ui_send
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow


async def _wait_state_response(session_id: str, *, needle: str):
    for _ in range(80):
        state = await get_container().workflow_runtime.get_state(session_id)
        if state is not None and state.response and needle in str(state.response):
            return state
        await asyncio.sleep(0.25)
    state = await get_container().workflow_runtime.get_state(session_id)
    raise AssertionError(
        f"response {needle!r} missing for {session_id}; state={state!r}"
    )


@pytest.mark.asyncio
async def test_a2a_flow_ui_bootstrap_and_autosync_do_not_run_graph(
    client: AsyncClient,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    _ = require_context()
    flow_id = f"a2a_flow_ui_{unique_id}"
    context_id = f"ctx-a2a-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    await create_echo_flow(client, flow_id)
    try:
        bootstrap = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-{unique_id}",
        )
        assert bootstrap["contextId"] == context_id
        assert bootstrap["status"]["state"] == "TASK_STATE_COMPLETED"

        sync = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id=f"sync-{unique_id}",
            revision=1,
            message_value=f"draft-{unique_id}",
        )
        assert sync["contextId"] == context_id
        assert sync["status"]["state"] == "TASK_STATE_COMPLETED"

        state = await get_container().workflow_runtime.get_state(session_id)
        assert state is not None
        assert state.ui_document.revision == 2
        assert state.ui_document.surfaces["main"].data_model.values["message"] == (
            f"draft-{unique_id}"
        )
        assert state.ui_interaction is None
        assert state.response is None or state.response == ""
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_a2a_flow_ui_submit_runs_echo_flow(
    client: AsyncClient,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    _ = require_context()
    flow_id = f"a2a_flow_ui_submit_{unique_id}"
    context_id = f"ctx-submit-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    await create_echo_flow(client, flow_id)
    try:
        _ = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-{uuid.uuid4().hex}",
        )
        _ = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id=f"sync-{uuid.uuid4().hex}",
            revision=1,
            message_value=f"ready-{unique_id}",
        )
        submitted = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SUBMIT_ACTION,
            context_id=context_id,
            action_id=f"submit-{uuid.uuid4().hex}",
            revision=2,
            message_value=f"run-{unique_id}",
        )
        assert submitted["status"]["state"] in {
            "TASK_STATE_COMPLETED",
            "TASK_STATE_WORKING",
            "TASK_STATE_SUBMITTED",
        }
        state = await _wait_state_response(session_id, needle=f"ECHO:run-{unique_id}")
        assert state.ui_document.revision >= 3
        assert state.ui_interaction is not None
    finally:
        await delete_flow(client, flow_id)


async def _create_ask_user_llm_flow(client: AsyncClient, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json={
            "flow_id": flow_id,
            "name": "Flow UI ask_user turn identity",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Use ask_user when you need a clarifying question.",
                    "tools": ["ask_user"],
                },
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_flow_ui_ask_user_resume_uses_new_task_id(
    client: AsyncClient,
    app: object,
    unique_id: str,
    mock_llm_with_queue: object,
    sync_tools: object,
) -> None:
    """
    Flow UI: ask_user INPUT_REQUIRED then second submit must open a new A2A Task
    (action-scoped id), not mutate the interrupted turn.
    """
    _ = app
    _ = sync_tools
    _ = require_context()
    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "What is your name?"},
            },
            "Hello, FlowUI!",
        ]
    )
    flow_id = f"a2a_flow_ui_ask_{unique_id}"
    context_id = f"ctx-ask-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    action_ask = f"submit-ask-{unique_id}"
    action_resume = f"submit-resume-{unique_id}"
    await _create_ask_user_llm_flow(client, flow_id)
    try:
        _ = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-{unique_id}",
        )
        _ = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id=f"sync-{unique_id}",
            revision=1,
            message_value="hi",
        )
        interrupted = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SUBMIT_ACTION,
            context_id=context_id,
            action_id=action_ask,
            revision=2,
            message_value="hi",
        )
        assert interrupted["status"]["state"] == "TASK_STATE_INPUT_REQUIRED", interrupted
        first_task_id = interrupted["id"]
        assert first_task_id == _flow_ui_task_id(context_id, action_ask)

        state_after_interrupt = await get_container().workflow_runtime.get_state(session_id)
        assert state_after_interrupt is not None
        assert state_after_interrupt.interrupt is not None
        assert state_after_interrupt.terminal_task_state == "input-required"
        resume_revision = state_after_interrupt.ui_document.revision

        resumed = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SUBMIT_ACTION,
            context_id=context_id,
            action_id=action_resume,
            revision=resume_revision,
            message_value="FlowUI",
        )
        second_task_id = resumed["id"]
        assert second_task_id == _flow_ui_task_id(context_id, action_resume)
        assert second_task_id != first_task_id, (
            f"Flow UI resume must not reuse interrupt task id: {first_task_id}"
        )
        assert resumed["status"]["state"] == "TASK_STATE_COMPLETED", resumed

        artifacts = resumed.get("artifacts") or []
        user_messages = [
            artifact
            for artifact in artifacts
            if isinstance(artifact, dict) and artifact.get("name") == "user_message"
        ]
        assert user_messages, f"resume Task must emit user_message, artifacts={artifacts!r}"
        mutation_ids: list[str] = []
        for artifact in user_messages:
            meta = artifact.get("metadata") or {}
            if not isinstance(meta, dict):
                continue
            for key in ("mutation_id", "mutationId"):
                value = meta.get(key)
                if isinstance(value, str):
                    mutation_ids.append(value)
        assert action_resume in mutation_ids, (
            f"user_message mutation_id must match submit action_id, got {mutation_ids!r}"
        )
    finally:
        await delete_flow(client, flow_id)

"""A2A HTTP bootstrap/sync for Flow UI without graph invocation."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient

from apps.flows.src.container import get_container
from core.a2a import (
    PLATFORM_UI_BOOTSTRAP_ACTION,
    PLATFORM_UI_SUBMIT_ACTION,
    PLATFORM_UI_SYNC_ACTION,
)
from core.context import require_context
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

"""Резолв session_id по task_id vs context_id для A2A cancel/get."""

from __future__ import annotations

import uuid

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.durable_execution import WorkflowEventType, create_initial_state


@pytest.mark.asyncio
async def test_runtime_resolve_by_task_id(app, unique_id: str) -> None:
    _ = app
    container = get_container()
    flow_id = f"flow-{unique_id}"
    context_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    session_id = f"{flow_id}:{context_id}"
    session_id_wrong = f"{flow_id}:{task_id}"

    state = create_initial_state(
        task_id=task_id,
        context_id=context_id,
        user_id="u1",
        session_id=session_id,
        content="hi",
    )
    await container.workflow_runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        snapshot=True,
    )
    assert await container.workflow_runtime.get_state(session_id_wrong) is None

    found = await container.workflow_runtime.resolve_session_id_by_flow_and_identifier(
        flow_id,
        task_id,
    )
    assert found == session_id

    found_ctx = await container.workflow_runtime.resolve_session_id_by_flow_and_identifier(
        flow_id,
        context_id,
    )
    assert found_ctx == session_id


@pytest.mark.asyncio
async def test_runtime_resolve_unknown(app) -> None:
    _ = app
    container = get_container()
    out = await container.workflow_runtime.resolve_session_id_by_flow_and_identifier(
        "f",
        "missing",
    )
    assert out is None

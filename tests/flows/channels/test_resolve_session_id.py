"""Резолв session_id по task_id vs context_id для A2A cancel/get."""

from __future__ import annotations

import uuid

import pytest

from apps.flows.src.db.state_repository import InMemoryStateRepository
from apps.flows.src.state.persistence import create_initial_state


@pytest.mark.asyncio
async def test_inmemory_resolve_by_task_id(unique_id: str) -> None:
    flow_id = "flow-x"
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
    repo = InMemoryStateRepository()
    await repo.set(session_id, state)
    assert await repo.get(session_id_wrong) is None

    found = await repo.resolve_session_id_by_flow_and_identifier(flow_id, task_id)
    assert found == session_id

    found_ctx = await repo.resolve_session_id_by_flow_and_identifier(
        flow_id, context_id
    )
    assert found_ctx == session_id


@pytest.mark.asyncio
async def test_inmemory_resolve_unknown() -> None:
    repo = InMemoryStateRepository()
    out = await repo.resolve_session_id_by_flow_and_identifier("f", "missing")
    assert out is None

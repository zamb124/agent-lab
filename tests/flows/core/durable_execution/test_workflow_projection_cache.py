"""Unit tests for workflow projection Redis cache TTL and terminal cleanup."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.flows.src.durable_execution.manager import (
    DurableWorkflowRuntime,
    _WORKFLOW_PROJECTION_CACHE_TTL_SECONDS,
)
from apps.flows.src.durable_execution.models import WorkflowStatus
from core.state import ExecutionState


class _RecordingRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []

    async def set(self, key: str, value: str, *, ttl: int) -> bool:
        self.set_calls.append((key, value, ttl))
        return True

    async def delete(self, *keys: str) -> int:
        self.delete_calls.extend(keys)
        return len(keys)


def _minimal_state() -> ExecutionState:
    return ExecutionState(
        task_id="task-1",
        context_id="ctx-1",
        user_id="user-1",
        session_id="flow:ctx-1",
    )


@pytest.mark.asyncio
async def test_projection_cache_sets_ttl_on_running() -> None:
    redis = _RecordingRedis()
    runtime = DurableWorkflowRuntime(repository=AsyncMock(), redis_client=redis)  # type: ignore[arg-type]
    state = _minimal_state()
    state_json = DurableWorkflowRuntime._dump_state(state)

    from apps.flows.src.durable_execution.hashing import hash_state_json

    computed_hash = hash_state_json(state_json)

    await runtime._cache_projection(  # noqa: SLF001
        company_id="company-1",
        session_id="flow:ctx-1",
        state=state,
        head_sequence=1,
        head_state_hash=computed_hash,
        execution_branch_id="branch-1",
        status=WorkflowStatus.running,
    )

    assert len(redis.set_calls) == 1
    key, _value, ttl = redis.set_calls[0]
    assert key == "flows:workflow_projection:company-1:flow:ctx-1"
    assert ttl == _WORKFLOW_PROJECTION_CACHE_TTL_SECONDS
    assert redis.delete_calls == []


@pytest.mark.asyncio
async def test_projection_cache_deleted_on_terminal() -> None:
    redis = _RecordingRedis()
    runtime = DurableWorkflowRuntime(repository=AsyncMock(), redis_client=redis)  # type: ignore[arg-type]
    state = _minimal_state()
    state_json = DurableWorkflowRuntime._dump_state(state)

    from apps.flows.src.durable_execution.hashing import hash_state_json

    computed_hash = hash_state_json(state_json)

    await runtime._cache_projection(  # noqa: SLF001
        company_id="company-1",
        session_id="flow:ctx-1",
        state=state,
        head_sequence=2,
        head_state_hash=computed_hash,
        execution_branch_id="branch-1",
        status=WorkflowStatus.completed,
    )

    assert redis.set_calls == []
    assert redis.delete_calls == ["flows:workflow_projection:company-1:flow:ctx-1"]

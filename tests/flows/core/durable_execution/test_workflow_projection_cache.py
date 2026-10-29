"""Unit tests for workflow projection Redis cache TTL and terminal cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.flows.src.durable_execution.manager import (
    _WORKFLOW_PROJECTION_CACHE_TTL_SECONDS,
    DurableWorkflowRuntime,
)
from apps.flows.src.durable_execution.models import (
    WorkflowInstance,
    WorkflowProjectionMismatchError,
    WorkflowStatus,
)
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
    runtime = DurableWorkflowRuntime(redis_client=redis)  # type: ignore[arg-type]
    state = _minimal_state()
    state_json = DurableWorkflowRuntime._dump_state(state)

    from apps.flows.src.durable_execution.hashing import hash_state_json

    computed_hash = hash_state_json(state_json)

    await runtime._cache_projection(  # noqa: SLF001
        company_id="company-1",
        session_id="flow:ctx-1",
        state_json=state_json,
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
    runtime = DurableWorkflowRuntime(redis_client=redis)  # type: ignore[arg-type]
    state = _minimal_state()
    state_json = DurableWorkflowRuntime._dump_state(state)

    from apps.flows.src.durable_execution.hashing import hash_state_json

    computed_hash = hash_state_json(state_json)

    await runtime._cache_projection(  # noqa: SLF001
        company_id="company-1",
        session_id="flow:ctx-1",
        state_json=state_json,
        head_sequence=2,
        head_state_hash=computed_hash,
        execution_branch_id="branch-1",
        status=WorkflowStatus.completed,
    )

    assert redis.set_calls == []
    assert redis.delete_calls == ["flows:workflow_projection:company-1:flow:ctx-1"]


@pytest.mark.asyncio
async def test_get_state_returns_rehydrated_state_on_projection_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read-path: mismatch при кешировании не роняет get_state — state из ledger отдаётся."""
    from apps.flows.src.durable_execution.hashing import hash_state_json

    state = _minimal_state()
    state_json = DurableWorkflowRuntime._dump_state(state)
    good_hash = hash_state_json(state_json)
    bad_hash = "0" * 64
    assert good_hash != bad_hash

    instance = MagicMock()
    instance.head_sequence = 3
    instance.head_state_hash = bad_hash
    instance.active_execution_branch_id = "branch-1"
    instance.status = WorkflowStatus.running.value

    async def _get_instance(**_kwargs: object) -> MagicMock:
        return instance

    async def _load_state_at_head(**_kwargs: object) -> tuple[ExecutionState, MagicMock]:
        return state, instance

    monkeypatch.setattr(WorkflowInstance, "any_by_company_and_session", _get_instance)
    monkeypatch.setattr(WorkflowInstance, "load_state_at_head", _load_state_at_head)

    redis = _RecordingRedis()

    async def _redis_get(_key: str) -> str | None:
        return None

    redis.get = _redis_get  # type: ignore[method-assign]

    runtime = DurableWorkflowRuntime(redis_client=redis)  # type: ignore[arg-type]
    runtime._company_id = lambda: "company-1"  # type: ignore[method-assign]

    loaded = await runtime.get_state("flow:ctx-1")
    assert loaded is not None
    assert loaded.session_id == "flow:ctx-1"
    assert "flows:workflow_projection:company-1:flow:ctx-1" in redis.delete_calls
    with pytest.raises(WorkflowProjectionMismatchError):
        await runtime._cache_projection(  # noqa: SLF001
            company_id="company-1",
            session_id="flow:ctx-1",
            state_json=state_json,
            head_sequence=3,
            head_state_hash=bad_hash,
            execution_branch_id="branch-1",
            status=WorkflowStatus.running,
        )

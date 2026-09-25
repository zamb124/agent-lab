"""HTTP-контракт durable branch operations: fork, rewind, manual-patch, retry."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.flows.src.durable_execution import (
    NodeFailedPayload,
    SuperstepCommittedPayload,
    SuperstepStartedPayload,
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.durable_execution.models import ExecutionBranchReason, WorkflowBranchResult
from core.context import Context, clear_context, set_context
from core.models.identity_models import User
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = pytest.mark.asyncio


def _user_input_payload(state: ExecutionState) -> UserInputAppliedPayload:
    return UserInputAppliedPayload(
        task_id=state.task_id,
        context_id=state.context_id,
        is_resume=False,
    )


def _manual_superstep_payload(step: str) -> SuperstepCommittedPayload:
    return SuperstepCommittedPayload(completed_nodes=[step], next_nodes=[])


def _branch_response_payload(response: Response, label: str) -> JsonObject:
    return require_json_object(cast(object, response.json()), label)


def _assert_branch_result(body: JsonObject, *, expected_reason: ExecutionBranchReason) -> WorkflowBranchResult:
    result = WorkflowBranchResult.model_validate(body)
    assert result.reason == expected_reason
    assert result.execution_branch_id
    assert result.state_hash
    assert result.snapshot_id
    assert result.effect.source_execution_branch_id
    assert result.effect.source_sequence >= 0
    assert result.effect.source_events_after_base >= 0
    assert result.effect.auto_resumes_run is False
    return result


async def _seed_three_step_session(unique_id: str, di) -> str:
    session_id = f"durable_api_{unique_id}:{uuid.uuid4().hex}"
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-api-user",
        session_id=session_id,
        content="one",
    )
    state.variables = {"step": 1}
    runtime = di.workflow_runtime

    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )
    state.content = "two"
    state.variables = {"step": 2}
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_committed,
        payload=_manual_superstep_payload("step-2"),
    )
    state.content = "three"
    state.variables = {"step": 3}
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_committed,
        payload=_manual_superstep_payload("step-3"),
    )
    return session_id


async def _seed_failed_session(unique_id: str, di) -> tuple[str, int]:
    session_id = f"durable_retry_{unique_id}:{uuid.uuid4().hex}"
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-api-user",
        session_id=session_id,
        content="start",
    )
    state.current_nodes = ["fragile_node"]
    runtime = di.workflow_runtime

    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_started,
        payload=SuperstepStartedPayload(current_nodes=["fragile_node"]),
        snapshot=True,
    )
    state.terminal_task_state = "failed"
    state.terminal_task_error = "boom"
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.node_failed,
        payload=NodeFailedPayload(
            failed_nodes=["fragile_node"],
            current_nodes=["fragile_node"],
            error="boom",
            recover_sequence=1,
            preserved_node_writes=[],
        ),
    )
    _ = await runtime.save_terminal_state(session_id, state, "failed", error="boom")
    history, _ = await runtime.get_state_history(session_id, limit=1000, offset=0)
    failed_events = [
        event for event in history if event.event_type == WorkflowEventType.node_failed
    ]
    if not failed_events:
        raise AssertionError("NodeFailed event was not persisted for retry test")
    return session_id, failed_events[-1].sequence


@pytest.fixture
def with_system_context() -> Callable[[], None]:
    def _enter() -> None:
        set_context(
            Context(
                user=User(user_id="durable_api_user", name="Durable API User"),
                active_company=make_test_company(
                    company_id="system",
                    name="System",
                    subdomain="system",
                ),
                session_id="durable_api_session",
                channel="test",
            )
        )

    return _enter


async def test_fork_returns_200_with_branch_result(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
    with_system_context: Callable[[], None],
    di,
) -> None:
    with_system_context()
    try:
        session_id = await _seed_three_step_session(unique_id, di=di)
    finally:
        clear_context()

    response = await flows_client.post(
        f"/flows/api/v1/tasks/{session_id}/fork",
        headers=auth_headers_system,
        json={"sequence": 1, "activate": False},
    )

    assert response.status_code == 200
    _ = _assert_branch_result(
        _branch_response_payload(response, "fork response"),
        expected_reason=ExecutionBranchReason.fork,
    )
    fork_result = WorkflowBranchResult.model_validate(
        _branch_response_payload(response, "fork response")
    )
    assert fork_result.effect.activates_head is False
    assert fork_result.effect.source_sequence == 1
    assert fork_result.effect.source_events_after_base == 2


async def test_rewind_returns_200_with_branch_result(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
    with_system_context: Callable[[], None],
    di,
) -> None:
    with_system_context()
    try:
        session_id = await _seed_three_step_session(unique_id, di=di)
    finally:
        clear_context()

    response = await flows_client.post(
        f"/flows/api/v1/tasks/{session_id}/rewind",
        headers=auth_headers_system,
        json={"sequence": 2},
    )

    assert response.status_code == 200
    body = _assert_branch_result(
        _branch_response_payload(response, "rewind response"),
        expected_reason=ExecutionBranchReason.rewind,
    )
    assert body.effect.activates_head is True
    assert body.effect.source_sequence == 2
    assert body.effect.source_events_after_base == 1
    assert body.effect.instance_status.value == "running"

    with_system_context()
    try:
        active = await di.workflow_runtime.get_state(session_id)
    finally:
        clear_context()
    assert active is not None
    assert active.content == "two"
    assert body.execution_branch_id


async def test_manual_patch_returns_200_with_branch_result(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
    with_system_context: Callable[[], None],
    di,
) -> None:
    with_system_context()
    try:
        session_id = await _seed_three_step_session(unique_id, di=di)
        runtime = di.workflow_runtime
        current = await runtime.get_state(session_id)
        assert current is not None
        history, total = await runtime.get_state_history(session_id, limit=1, offset=0)
        if total > 1:
            history, _ = await runtime.get_state_history(
                session_id,
                limit=1,
                offset=total - 1,
            )
        head_sequence = history[-1].sequence if history else 0
        patched_state = ExecutionState.model_validate(
            current.model_dump(mode="json", exclude_none=False)
        )
        patched_state.content = "patched-via-api"
    finally:
        clear_context()

    response = await flows_client.post(
        f"/flows/api/v1/tasks/{session_id}/manual-patch",
        headers=auth_headers_system,
        json={
            "sequence": head_sequence,
            "state": patched_state.model_dump(mode="json", exclude_none=False),
            "activate": True,
        },
    )

    assert response.status_code == 200
    _ = _assert_branch_result(
        _branch_response_payload(response, "manual-patch response"),
        expected_reason=ExecutionBranchReason.manual_patch,
    )


async def test_retry_from_failure_returns_200_with_branch_result(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
    with_system_context: Callable[[], None],
    di,
) -> None:
    with_system_context()
    try:
        session_id, failed_sequence = await _seed_failed_session(unique_id, di=di)
    finally:
        clear_context()

    response = await flows_client.post(
        f"/flows/api/v1/tasks/{session_id}/retry-from-failure",
        headers=auth_headers_system,
        json={"failed_sequence": failed_sequence},
    )

    assert response.status_code == 200
    _ = _assert_branch_result(
        _branch_response_payload(response, "retry response"),
        expected_reason=ExecutionBranchReason.retry,
    )

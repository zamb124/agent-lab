"""Prod-like: durable history/time-travel — REST и `op_*` один handler."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.durable_operations import (
    op_flows_durable_branches,
    op_flows_durable_fork,
    op_flows_durable_history,
    op_flows_durable_rewind,
    op_flows_sessions_state,
    op_flows_sessions_state_update,
)
from apps.flows.src.durable_execution import (
    SuperstepCommittedPayload,
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.durable_execution.models import ExecutionBranchReason, WorkflowBranchResult
from apps.flows.src.models.durable_api import (
    DurableForkPayload,
    DurableHistoryPayload,
    DurableRewindPayload,
    DurableSessionIdPayload,
    DurableSessionStatePayload,
    DurableSessionStateUpdatePayload,
    WorkflowBranchesResponse,
    WorkflowHistoryResponse,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.state import ExecutionState
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


def _user_input_payload(state: ExecutionState) -> UserInputAppliedPayload:
    return UserInputAppliedPayload(
        task_id=state.task_id,
        context_id=state.context_id,
        is_resume=False,
    )


def _manual_superstep_payload(step: str) -> SuperstepCommittedPayload:
    return SuperstepCommittedPayload(completed_nodes=[step], next_nodes=[])


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def _seed_three_step_session(di: FlowsDi, unique_id: str) -> str:
    session_id = f"durable_cmd_{unique_id}:{uuid.uuid4().hex}"
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-cmd-user",
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


async def test_durable_history_and_state_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    with _system_scope(system_user_id):
        session_id = await _seed_three_step_session(di, unique_id)

    history_http = await client.get(
        f"/flows/api/v1/tasks/{session_id}/history",
        headers=auth_headers_system,
    )
    assert history_http.status_code == 200, history_http.text
    history_body = WorkflowHistoryResponse.model_validate(history_http.json())
    assert history_body.total >= 3
    assert history_body.limit == 200
    assert history_body.offset == 0

    state_http = await client.get(
        "/flows/api/v1/tasks/state",
        headers=auth_headers_system,
        params={"session_id": session_id},
    )
    assert state_http.status_code == 200, state_http.text
    assert state_http.json()["content"] == "three"

    branches_http = await client.get(
        f"/flows/api/v1/tasks/{session_id}/branches",
        headers=auth_headers_system,
    )
    assert branches_http.status_code == 200, branches_http.text

    with _system_scope(system_user_id) as user:
        history = await op_flows_durable_history(
            DurableHistoryPayload(session_id=session_id, limit=200, offset=0),
            user=user,
            di=di,
        )
        assert history.model_dump(mode="json") == history_http.json()
        state = await op_flows_sessions_state(
            DurableSessionStatePayload(session_id=session_id),
            user=user,
            di=di,
        )
        assert state.model_dump(mode="json") == state_http.json()
        branches = await op_flows_durable_branches(
            DurableSessionIdPayload(session_id=session_id),
            user=user,
            di=di,
        )
        assert branches.model_dump(mode="json") == branches_http.json()
        _ = WorkflowBranchesResponse.model_validate(branches_http.json())


async def test_durable_fork_and_rewind_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    with _system_scope(system_user_id):
        fork_session_id = await _seed_three_step_session(di, f"{unique_id}_fork")
        rewind_rest_session_id = await _seed_three_step_session(di, f"{unique_id}_rewind_rest")
        rewind_op_session_id = await _seed_three_step_session(di, f"{unique_id}_rewind_op")

    fork_http = await client.post(
        f"/flows/api/v1/tasks/{fork_session_id}/fork",
        headers=auth_headers_system,
        json={"sequence": 1, "activate": False},
    )
    assert fork_http.status_code == 200, fork_http.text
    fork_rest = WorkflowBranchResult.model_validate(fork_http.json())
    assert fork_rest.reason == ExecutionBranchReason.fork
    assert fork_rest.effect.activates_head is False
    assert fork_rest.effect.source_sequence == 1

    rewind_http = await client.post(
        f"/flows/api/v1/tasks/{rewind_rest_session_id}/rewind",
        headers=auth_headers_system,
        json={"sequence": 2},
    )
    assert rewind_http.status_code == 200, rewind_http.text
    rewind_rest = WorkflowBranchResult.model_validate(rewind_http.json())
    assert rewind_rest.reason == ExecutionBranchReason.rewind
    assert rewind_rest.effect.activates_head is True
    assert rewind_rest.effect.source_sequence == 2

    with _system_scope(system_user_id) as user:
        fork_op = await op_flows_durable_fork(
            DurableForkPayload(session_id=fork_session_id, sequence=1, activate=False),
            user=user,
            di=di,
        )
        assert fork_op.reason == ExecutionBranchReason.fork
        assert fork_op.effect.activates_head is False
        assert fork_op.effect.source_sequence == 1
        rewind_op = await op_flows_durable_rewind(
            DurableRewindPayload(session_id=rewind_op_session_id, sequence=2),
            user=user,
            di=di,
        )
        assert rewind_op.reason == ExecutionBranchReason.rewind
        assert rewind_op.effect.source_sequence == 2
        state = await op_flows_sessions_state(
            DurableSessionStatePayload(session_id=rewind_op_session_id),
            user=user,
            di=di,
        )
        assert state.content == "two"


async def test_session_state_missing_is_not_found(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    missing_session_id = f"durable_missing_{unique_id}:{unique_id}"
    missing_http = await client.get(
        "/flows/api/v1/tasks/state",
        headers=auth_headers_system,
        params={"session_id": missing_session_id},
    )
    assert missing_http.status_code == 404, missing_http.text

    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as exc_info:
            _ = await op_flows_sessions_state(
                DurableSessionStatePayload(session_id=missing_session_id),
                user=user,
                di=di,
            )
    assert exc_info.value.code == "not_found"


async def test_session_state_update_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    with _system_scope(system_user_id):
        rest_session_id = await _seed_three_step_session(di, f"{unique_id}_put_rest")
        op_session_id = await _seed_three_step_session(di, f"{unique_id}_put_op")

    rest_state = await di.workflow_runtime.get_state(rest_session_id)
    assert rest_state is not None
    rest_state.content = "patched-rest"
    rest_http = await client.put(
        "/flows/api/v1/tasks/state",
        headers=auth_headers_system,
        params={"session_id": rest_session_id},
        json={"state": rest_state.model_dump(mode="json")},
    )
    assert rest_http.status_code == 200, rest_http.text
    assert rest_http.json()["content"] == "patched-rest"

    op_state = await di.workflow_runtime.get_state(op_session_id)
    assert op_state is not None
    op_state.content = "patched-op"
    with _system_scope(system_user_id) as user:
        updated = await op_flows_sessions_state_update(
            DurableSessionStateUpdatePayload(session_id=op_session_id, state=op_state),
            user=user,
            di=di,
        )
        current = await op_flows_sessions_state(
            DurableSessionStatePayload(session_id=op_session_id),
            user=user,
            di=di,
        )
    assert updated.content == "patched-op"
    assert current.model_dump(mode="json") == updated.model_dump(mode="json")

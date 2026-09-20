"""Durable history и time-travel: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from typing import Never

from apps.flows.realtime.operations import (
    raise_conflict,
    raise_invalid,
    raise_not_found,
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.durable_execution.models import WorkflowBranchResult
from apps.flows.src.durable_execution.repository import WorkflowConcurrencyError
from apps.flows.src.models.durable_api import (
    DurableForkPayload,
    DurableHistoryPayload,
    DurableManualPatchPayload,
    DurableRetryPayload,
    DurableRewindPayload,
    DurableSessionIdPayload,
    DurableSessionStatePayload,
    DurableSessionStateUpdatePayload,
    DurableStateAtPayload,
    WorkflowBranchesResponse,
    WorkflowHistoryResponse,
)
from core.models.identity_models import User
from core.state import ExecutionState
from core.websocket import WsCommandError


def _raise_durable(exc: Exception) -> Never:
    if isinstance(exc, WorkflowConcurrencyError):
        raise_conflict(exc)
    message = str(exc)
    if "not found" in message:
        raise_not_found(exc)
    if isinstance(exc, RuntimeError):
        raise WsCommandError("internal", str(exc)) from exc
    raise_invalid(exc)


def _resolved_session_id(payload: DurableSessionStatePayload) -> str:
    if payload.session_id is not None:
        return payload.session_id
    if payload.flow_id is None or payload.context_id is None:
        raise_invalid(ValueError("Need session_id or context_id+flow_id"))
    return f"{payload.flow_id}:{payload.context_id}"


async def op_flows_sessions_state(
    payload: DurableSessionStatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> ExecutionState:
    _ = user
    _ = await require_company_member(container)
    session_id = _resolved_session_id(payload)
    state = await container.workflow_runtime.get_state(session_id)
    if state is None:
        raise_not_found(LookupError("State not found"))
    return state


async def op_flows_sessions_state_update(
    payload: DurableSessionStateUpdatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> ExecutionState:
    _ = user
    _ = await require_company_member(container)
    session_id = _resolved_session_id(payload)
    current = await container.workflow_runtime.get_state(session_id)
    if current is None:
        raise_not_found(LookupError("Workflow session not found"))
    history, total = await container.workflow_runtime.get_state_history(
        session_id,
        limit=1,
        offset=0,
    )
    if total > 1:
        history, _ = await container.workflow_runtime.get_state_history(
            session_id,
            limit=1,
            offset=total - 1,
        )
    head_sequence = history[-1].sequence if history else 0
    try:
        _ = await container.workflow_runtime.patch_state_at_sequence(
            session_id,
            head_sequence,
            payload.state,
        )
    except (ValueError, RuntimeError) as exc:
        _raise_durable(exc)
    updated_state = await container.workflow_runtime.get_state(session_id)
    if updated_state is None:
        raise WsCommandError("internal", "Failed to save state")
    return updated_state


async def op_flows_durable_history(
    payload: DurableHistoryPayload,
    *,
    user: User,
    container: FlowContainer,
) -> WorkflowHistoryResponse:
    _ = user
    _ = await require_company_member(container)
    events, total = await container.workflow_runtime.get_state_history(
        payload.session_id,
        execution_branch_id=payload.execution_branch_id,
        limit=payload.limit,
        offset=payload.offset,
    )
    return WorkflowHistoryResponse(
        events=events,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_durable_branches(
    payload: DurableSessionIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> WorkflowBranchesResponse:
    _ = user
    _ = await require_company_member(container)
    branches = await container.workflow_runtime.list_branches(payload.session_id)
    return WorkflowBranchesResponse(branches=branches)


async def op_flows_durable_state_at(
    payload: DurableStateAtPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ExecutionState:
    _ = user
    _ = await require_company_member(container)
    if payload.session_id == "":
        raise_invalid(ValueError("session_id required"))
    state = await container.workflow_runtime.load_state_at_sequence(
        payload.session_id,
        payload.sequence,
        execution_branch_id=payload.execution_branch_id,
    )
    if state is None:
        raise_not_found(LookupError("State projection not found"))
    return state


async def op_flows_durable_fork(
    payload: DurableForkPayload,
    *,
    user: User,
    container: FlowContainer,
) -> WorkflowBranchResult:
    _ = user
    _ = await require_company_member(container)
    if payload.session_id == "":
        raise_invalid(ValueError("session_id required"))
    try:
        return await container.workflow_runtime.fork_state_at_sequence(
            payload.session_id,
            payload.sequence,
            execution_branch_id=payload.execution_branch_id,
            activate=payload.activate,
        )
    except (ValueError, RuntimeError) as exc:
        _raise_durable(exc)


async def op_flows_durable_rewind(
    payload: DurableRewindPayload,
    *,
    user: User,
    container: FlowContainer,
) -> WorkflowBranchResult:
    _ = user
    _ = await require_company_member(container)
    if payload.session_id == "":
        raise_invalid(ValueError("session_id required"))
    try:
        return await container.workflow_runtime.rewind_to_sequence(
            payload.session_id,
            payload.sequence,
            execution_branch_id=payload.execution_branch_id,
        )
    except (ValueError, RuntimeError) as exc:
        _raise_durable(exc)


async def op_flows_durable_manual_patch(
    payload: DurableManualPatchPayload,
    *,
    user: User,
    container: FlowContainer,
) -> WorkflowBranchResult:
    _ = user
    _ = await require_company_member(container)
    if payload.session_id == "":
        raise_invalid(ValueError("session_id required"))
    try:
        return await container.workflow_runtime.patch_state_at_sequence(
            payload.session_id,
            payload.sequence,
            payload.state,
            execution_branch_id=payload.execution_branch_id,
            activate=payload.activate,
        )
    except (ValueError, RuntimeError) as exc:
        _raise_durable(exc)


async def op_flows_durable_retry_from_failure(
    payload: DurableRetryPayload,
    *,
    user: User,
    container: FlowContainer,
) -> WorkflowBranchResult:
    _ = user
    _ = await require_company_member(container)
    if payload.session_id == "":
        raise_invalid(ValueError("session_id required"))
    try:
        return await container.workflow_runtime.retry_from_failure(
            payload.session_id,
            failed_sequence=payload.failed_sequence,
            execution_branch_id=payload.execution_branch_id,
        )
    except (ValueError, RuntimeError) as exc:
        _raise_durable(exc)

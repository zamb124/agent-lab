"""Code agent: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Never, TypeVar

from apps.flows.realtime.operations import (
    require_edit_flow,
    require_view_flow,
)
from apps.flows.src.container import FlowContainer
from core.guest_runtime.models import (
    CodeAgentCopyTreeRequest,
    CodeAgentDeletePayload,
    CodeAgentEnsureSourceResponse,
    CodeAgentImportArchiveRequest,
    CodeAgentImportGitRequest,
    CodeAgentLogsPayload,
    CodeAgentNodeRefPayload,
    CodeAgentNodeStatusResponse,
    CodeAgentRebuildRequest,
    GuestBuildBusyError,
    GuestLeaseCapError,
    GuestRebuildResponse,
    GuestRuntimeLogsResponse,
    GuestRuntimeUnavailableError,
)
from core.models.identity_models import User
from core.websocket import (
    WsCommandError,
    raise_conflict,
    raise_invalid,
    raise_not_found,
    raise_unavailable,
)

T = TypeVar("T")


def raise_code_agent(exc: Exception) -> Never:
    if isinstance(exc, GuestRuntimeUnavailableError):
        raise_unavailable(exc)
    if isinstance(exc, GuestLeaseCapError | GuestBuildBusyError):
        raise_conflict(exc)
    if isinstance(exc, LookupError):
        raise_not_found(exc)
    if isinstance(exc, RuntimeError):
        raise WsCommandError("internal", str(exc)) from exc
    raise_invalid(exc)


async def _run_code_agent(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except (
        LookupError,
        ValueError,
        RuntimeError,
        GuestRuntimeUnavailableError,
        GuestLeaseCapError,
        GuestBuildBusyError,
    ) as exc:
        raise_code_agent(exc)


def _resolved_branch_id(branch_id: str) -> str:
    if branch_id in {"", "base"}:
        return "default"
    return branch_id


def _require_node_ref(payload: CodeAgentNodeRefPayload) -> tuple[str, str, str]:
    if payload.flow_id == "":
        raise_invalid(ValueError("flow_id required"))
    if payload.node_id == "":
        raise_invalid(ValueError("node_id required"))
    return payload.flow_id, payload.node_id, _resolved_branch_id(payload.branch_id)


async def op_flows_code_agent_ensure_source(
    payload: CodeAgentNodeRefPayload,
    *,
    user: User,
    container: FlowContainer,
) -> CodeAgentEnsureSourceResponse:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_edit_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.ensure_source(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
    )


async def op_flows_code_agent_import_git(
    payload: CodeAgentImportGitRequest,
    *,
    user: User,
    container: FlowContainer,
) -> CodeAgentNodeStatusResponse:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_edit_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.import_git(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            git_url=payload.git_url,
            source_sha=payload.source_sha,
        )
    )


async def op_flows_code_agent_import_archive(
    payload: CodeAgentImportArchiveRequest,
    *,
    user: User,
    container: FlowContainer,
) -> CodeAgentNodeStatusResponse:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_edit_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.import_archive(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            file_id=payload.file_id,
        )
    )


async def op_flows_code_agent_copy_tree(
    payload: CodeAgentCopyTreeRequest,
    *,
    user: User,
    container: FlowContainer,
) -> CodeAgentEnsureSourceResponse:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_edit_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.copy_tree(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            from_catalog_id=payload.from_catalog_id,
        )
    )


async def op_flows_code_agent_rebuild(
    payload: CodeAgentRebuildRequest,
    *,
    user: User,
    container: FlowContainer,
) -> GuestRebuildResponse:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_edit_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.rebuild(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            request=payload,
        )
    )


async def op_flows_code_agent_status(
    payload: CodeAgentNodeRefPayload,
    *,
    user: User,
    container: FlowContainer,
) -> CodeAgentNodeStatusResponse:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_view_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.status(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
    )


async def op_flows_code_agent_logs(
    payload: CodeAgentLogsPayload,
    *,
    user: User,
    container: FlowContainer,
) -> GuestRuntimeLogsResponse:
    _ = user
    flow_id, node_id, _branch_id = _require_node_ref(payload)
    _ = await require_view_flow(container, flow_id)
    return await _run_code_agent(
        container.code_agent_source_service.logs(
            flow_id=flow_id,
            node_id=node_id,
            task_id=payload.task_id,
            session_id=payload.session_id,
            context_id=payload.context_id,
        )
    )


async def op_flows_code_agent_delete(
    payload: CodeAgentDeletePayload,
    *,
    user: User,
    container: FlowContainer,
) -> None:
    _ = user
    flow_id, node_id, branch_id = _require_node_ref(payload)
    _ = await require_edit_flow(container, flow_id)
    await _run_code_agent(
        container.code_agent_source_service.delete_source(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            catalog_id=payload.catalog_id,
        )
    )

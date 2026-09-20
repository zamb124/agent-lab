"""REST-зеркало code_agent: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.realtime.code_agent_operations import (
    op_flows_code_agent_copy_tree,
    op_flows_code_agent_delete,
    op_flows_code_agent_ensure_source,
    op_flows_code_agent_import_archive,
    op_flows_code_agent_import_git,
    op_flows_code_agent_logs,
    op_flows_code_agent_rebuild,
    op_flows_code_agent_status,
)
from apps.flows.src.dependencies import ContainerDep
from core.context import require_context
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
    GuestRebuildResponse,
    GuestRuntimeLogsResponse,
)

router = APIRouter(tags=["code-agent"])


@router.post(
    "/{flow_id}/nodes/{node_id}/code-agent/ensure-source",
    response_model=CodeAgentEnsureSourceResponse,
)
async def ensure_code_agent_source(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
) -> CodeAgentEnsureSourceResponse:
    return await op_flows_code_agent_ensure_source(
        CodeAgentNodeRefPayload(flow_id=flow_id, node_id=node_id, branch_id=branch_id),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/{flow_id}/nodes/{node_id}/code-agent/import-git",
    response_model=CodeAgentNodeStatusResponse,
)
async def import_code_agent_git(
    flow_id: str,
    node_id: str,
    body: CodeAgentImportGitRequest,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
) -> CodeAgentNodeStatusResponse:
    return await op_flows_code_agent_import_git(
        body.model_copy(update={"flow_id": flow_id, "node_id": node_id, "branch_id": branch_id}),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/{flow_id}/nodes/{node_id}/code-agent/import-archive",
    response_model=CodeAgentNodeStatusResponse,
)
async def import_code_agent_archive(
    flow_id: str,
    node_id: str,
    body: CodeAgentImportArchiveRequest,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
) -> CodeAgentNodeStatusResponse:
    return await op_flows_code_agent_import_archive(
        body.model_copy(update={"flow_id": flow_id, "node_id": node_id, "branch_id": branch_id}),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/{flow_id}/nodes/{node_id}/code-agent/copy-tree",
    response_model=CodeAgentEnsureSourceResponse,
)
async def copy_code_agent_tree(
    flow_id: str,
    node_id: str,
    body: CodeAgentCopyTreeRequest,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
) -> CodeAgentEnsureSourceResponse:
    return await op_flows_code_agent_copy_tree(
        body.model_copy(update={"flow_id": flow_id, "node_id": node_id, "branch_id": branch_id}),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/{flow_id}/nodes/{node_id}/code-agent/rebuild",
    response_model=GuestRebuildResponse,
)
async def rebuild_code_agent(
    flow_id: str,
    node_id: str,
    body: CodeAgentRebuildRequest,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
) -> GuestRebuildResponse:
    return await op_flows_code_agent_rebuild(
        body.model_copy(update={"flow_id": flow_id, "node_id": node_id, "branch_id": branch_id}),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/{flow_id}/nodes/{node_id}/code-agent",
    response_model=CodeAgentNodeStatusResponse,
)
async def code_agent_status(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
) -> CodeAgentNodeStatusResponse:
    return await op_flows_code_agent_status(
        CodeAgentNodeRefPayload(flow_id=flow_id, node_id=node_id, branch_id=branch_id),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/{flow_id}/nodes/{node_id}/code-agent/logs",
    response_model=GuestRuntimeLogsResponse,
)
async def code_agent_logs(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
    task_id: Annotated[str | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    context_id: Annotated[str | None, Query()] = None,
) -> GuestRuntimeLogsResponse:
    return await op_flows_code_agent_logs(
        CodeAgentLogsPayload(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            task_id=task_id,
            session_id=session_id,
            context_id=context_id,
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/{flow_id}/nodes/{node_id}/code-agent", status_code=204)
async def delete_code_agent_source(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
    catalog_id: Annotated[str | None, Query()] = None,
) -> None:
    return await op_flows_code_agent_delete(
        CodeAgentDeletePayload(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            catalog_id=catalog_id,
        ),
        user=require_context().user,
        container=container,
    )

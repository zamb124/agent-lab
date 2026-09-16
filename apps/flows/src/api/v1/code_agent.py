"""HTTP: дерево исходников code_agent и rebuild на ферме."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from core.authz.models import AuthzObject
from core.context import require_active_company, require_context
from core.guest_runtime.models import (
    CodeAgentCopyTreeRequest,
    CodeAgentEnsureSourceResponse,
    CodeAgentImportArchiveRequest,
    CodeAgentImportGitRequest,
    CodeAgentNodeStatusResponse,
    CodeAgentRebuildRequest,
    GuestBuildBusyError,
    GuestLeaseCapError,
    GuestRebuildResponse,
    GuestRuntimeLogsResponse,
)

router = APIRouter(tags=["code-agent"])


def _actor_user_id() -> str:
    return require_context().user.user_id


def _flow_obj(flow_id: str) -> AuthzObject:
    return AuthzObject.flow(flow_id, company_id=require_active_company().company_id)


async def _require_view_flow(container: ContainerDep, flow_id: str) -> None:
    await container.authz_service.require_can_view(_flow_obj(flow_id), user_id=_actor_user_id())


async def _require_edit_flow(container: ContainerDep, flow_id: str) -> None:
    await container.authz_service.require_can_edit(_flow_obj(flow_id), user_id=_actor_user_id())


def _http_from_source_error(exc: LookupError | ValueError) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _http_from_farm_error(exc: GuestLeaseCapError | GuestBuildBusyError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


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
    await _require_edit_flow(container, flow_id)
    try:
        return await container.code_agent_source_service.ensure_source(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


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
    await _require_edit_flow(container, flow_id)
    try:
        return await container.code_agent_source_service.import_git(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            git_url=body.git_url,
            source_sha=body.source_sha,
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


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
    await _require_edit_flow(container, flow_id)
    try:
        return await container.code_agent_source_service.import_archive(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            file_id=body.file_id,
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


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
    await _require_edit_flow(container, flow_id)
    try:
        return await container.code_agent_source_service.copy_tree(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            from_catalog_id=body.from_catalog_id,
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


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
    await _require_edit_flow(container, flow_id)
    try:
        return await container.code_agent_source_service.rebuild(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id, request=body
        )
    except (GuestLeaseCapError, GuestBuildBusyError) as exc:
        raise _http_from_farm_error(exc) from exc
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


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
    await _require_view_flow(container, flow_id)
    try:
        return await container.code_agent_source_service.status(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


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
    await _require_view_flow(container, flow_id)
    _ = branch_id
    try:
        return await container.code_agent_source_service.logs(
            flow_id=flow_id,
            node_id=node_id,
            task_id=task_id,
            session_id=session_id,
            context_id=context_id,
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc


@router.delete("/{flow_id}/nodes/{node_id}/code-agent", status_code=204)
async def delete_code_agent_source(
    flow_id: str,
    node_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query()] = "default",
    catalog_id: Annotated[str | None, Query()] = None,
) -> None:
    await _require_edit_flow(container, flow_id)
    try:
        await container.code_agent_source_service.delete_source(
            flow_id=flow_id,
            node_id=node_id,
            branch_id=branch_id,
            catalog_id=catalog_id,
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_source_error(exc) from exc

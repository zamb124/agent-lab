"""REST-зеркало каталога flows: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.realtime.operations import (
    FlowDataflowInspectRequest,
    FlowsFlowIdPayload,
    FlowsFlowVersionPayload,
    FlowsListPayload,
    op_flows_create,
    op_flows_dataflow_inspect,
    op_flows_item,
    op_flows_list,
    op_flows_metadata_update,
    op_flows_nodes_bulk_delete,
    op_flows_preview_share,
    op_flows_reload_from_bundle,
    op_flows_remove,
    op_flows_store_bundles,
    op_flows_update,
    op_flows_validate,
    op_flows_version_item,
    op_flows_version_rollback,
    op_flows_versions_list,
    op_flows_voice_session_query,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import DataflowInspectResult, FlowType
from apps.flows.src.models.flow_api import (
    BulkDeleteNodesRequest,
    BulkDeleteNodesResponse,
    FlowCreateRequest,
    FlowDeletedResponse,
    FlowMetadataRequest,
    FlowMetadataResponse,
    FlowPreviewShareRequest,
    FlowPreviewShareResponse,
    FlowResponse,
    FlowStoreBundleResponse,
    FlowValidateRequest,
    FlowValidateResponse,
    FlowVersionRollbackResponse,
    FlowVoiceSessionQueryRequest,
    FlowVoiceSessionQueryResponse,
    ReloadFlowFromBundleResponse,
)
from core.context import require_context
from core.pagination import ListResponse, OffsetPage
from core.websocket import EmptyPayload

router = APIRouter(tags=["flows"])


@router.post("/dataflow/inspect")
async def inspect_dataflow(
    request: FlowDataflowInspectRequest,
    container: ContainerDep,
) -> DataflowInspectResult:
    return await op_flows_dataflow_inspect(
        request, user=require_context().user, container=container
    )


@router.post("/validate", response_model=FlowValidateResponse)
async def validate_flow(
    request: FlowValidateRequest,
    container: ContainerDep,
) -> FlowValidateResponse:
    return await op_flows_validate(
        request, user=require_context().user, container=container
    )


@router.get("", response_model=OffsetPage[FlowResponse])
@router.get("/", response_model=OffsetPage[FlowResponse])
async def list_flows(
    container: ContainerDep,
    type: FlowType | None = None,
    limit: Annotated[int, Query(ge=1, le=2000, description="Максимум flows")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
) -> OffsetPage[FlowResponse]:
    return await op_flows_list(
        FlowsListPayload(type=type, limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.get("/store/bundles", response_model=ListResponse[FlowStoreBundleResponse])
async def list_store_bundles(container: ContainerDep) -> ListResponse[FlowStoreBundleResponse]:
    return await op_flows_store_bundles(
        EmptyPayload(),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=FlowResponse)
@router.post("/", response_model=FlowResponse)
async def create_flow(request: FlowCreateRequest, container: ContainerDep) -> FlowResponse:
    return await op_flows_create(
        request,
        user=require_context().user,
        container=container,
    )


@router.get("/{flow_id}/voice-session-query", response_model=FlowVoiceSessionQueryResponse)
async def get_flow_voice_session_query(
    flow_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query(description="ID ветки графа для мержа speech")] = "default",
) -> FlowVoiceSessionQueryResponse:
    return await op_flows_voice_session_query(
        FlowVoiceSessionQueryRequest(flow_id=flow_id, branch_id=branch_id),
        user=require_context().user,
        container=container,
    )


@router.get("/{flow_id}", response_model=FlowResponse)
async def get_flow(flow_id: str, container: ContainerDep) -> FlowResponse:
    return await op_flows_item(
        FlowsFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        container=container,
    )


@router.post("/{flow_id}/reload-from-bundle", response_model=ReloadFlowFromBundleResponse)
async def reload_flow_from_bundle(
    flow_id: str,
    container: ContainerDep,
) -> ReloadFlowFromBundleResponse:
    return await op_flows_reload_from_bundle(
        FlowsFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        container=container,
    )


@router.post("/{flow_id}/preview-share", response_model=FlowPreviewShareResponse)
async def create_flow_preview_share(
    flow_id: str,
    body: FlowPreviewShareRequest,
    container: ContainerDep,
) -> FlowPreviewShareResponse:
    payload = body.model_copy(update={"flow_id": flow_id})
    return await op_flows_preview_share(
        payload,
        user=require_context().user,
        container=container,
    )


@router.put("/{flow_id}", response_model=FlowResponse)
async def update_flow(
    flow_id: str,
    request: FlowCreateRequest,
    container: ContainerDep,
) -> FlowResponse:
    payload = request.model_copy(update={"flow_id": flow_id})
    return await op_flows_update(
        payload,
        user=require_context().user,
        container=container,
    )


@router.post("/{flow_id}/nodes/bulk_delete", response_model=BulkDeleteNodesResponse)
async def bulk_delete_nodes(
    flow_id: str,
    request: BulkDeleteNodesRequest,
    container: ContainerDep,
) -> BulkDeleteNodesResponse:
    payload = request.model_copy(update={"flow_id": flow_id})
    return await op_flows_nodes_bulk_delete(
        payload,
        user=require_context().user,
        container=container,
    )


@router.patch("/{flow_id}/metadata", response_model=FlowMetadataResponse)
async def update_flow_metadata(
    flow_id: str,
    request: FlowMetadataRequest,
    container: ContainerDep,
) -> FlowMetadataResponse:
    payload = request.model_copy(update={"flow_id": flow_id})
    return await op_flows_metadata_update(
        payload,
        user=require_context().user,
        container=container,
    )


@router.delete("/{flow_id}", response_model=FlowDeletedResponse)
async def delete_flow(flow_id: str, container: ContainerDep) -> FlowDeletedResponse:
    return await op_flows_remove(
        FlowsFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        container=container,
    )


@router.get("/{flow_id}/versions", response_model=ListResponse[str])
async def list_versions(flow_id: str, container: ContainerDep) -> ListResponse[str]:
    return await op_flows_versions_list(
        FlowsFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        container=container,
    )


@router.get("/{flow_id}/versions/{version}", response_model=FlowResponse)
async def get_version(
    flow_id: str,
    version: str,
    container: ContainerDep,
) -> FlowResponse:
    return await op_flows_version_item(
        FlowsFlowVersionPayload(flow_id=flow_id, version=version),
        user=require_context().user,
        container=container,
    )


@router.post("/{flow_id}/versions/{version}/rollback", response_model=FlowVersionRollbackResponse)
async def rollback_version(
    flow_id: str,
    version: str,
    container: ContainerDep,
) -> FlowVersionRollbackResponse:
    return await op_flows_version_rollback(
        FlowsFlowVersionPayload(flow_id=flow_id, version=version),
        user=require_context().user,
        container=container,
    )

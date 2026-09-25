"""REST-зеркало shared resources: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.di import Di
from apps.flows.realtime.resource_operations import (
    op_flows_resources_create,
    op_flows_resources_item,
    op_flows_resources_list,
    op_flows_resources_remove,
    op_flows_resources_update,
)
from apps.flows.src.models.resource import (
    ResourceDefinition,
    ResourceDeletedResponse,
    ResourceIdPayload,
    ResourceListPayload,
    ResourceType,
    ResourceUpdatePayload,
    ResourceUpdateRequest,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(tags=["resources"])


@router.get("", response_model=OffsetPage[ResourceDefinition])
@router.get("/", response_model=OffsetPage[ResourceDefinition])
async def list_resources(
    di: Di,
    resource_type: Annotated[ResourceType | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ResourceDefinition]:
    return await op_flows_resources_list(
        ResourceListPayload(limit=limit, offset=offset, type=resource_type),
        user=require_context().user,
        di=di,
    )


@router.get("/{resource_id}", response_model=ResourceDefinition)
async def get_resource(
    resource_id: str,
    di: Di,
) -> ResourceDefinition:
    return await op_flows_resources_item(
        ResourceIdPayload(resource_id=resource_id),
        user=require_context().user,
        di=di,
    )


@router.post("", response_model=ResourceDefinition)
@router.post("/", response_model=ResourceDefinition)
async def create_resource(
    body: ResourceDefinition,
    di: Di,
) -> ResourceDefinition:
    return await op_flows_resources_create(
        body,
        user=require_context().user,
        di=di,
    )


@router.put("/{resource_id}", response_model=ResourceDefinition)
async def update_resource(
    resource_id: str,
    body: ResourceUpdateRequest,
    di: Di,
) -> ResourceDefinition:
    return await op_flows_resources_update(
        ResourceUpdatePayload.model_validate(
            {"resource_id": resource_id, **body.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{resource_id}", response_model=ResourceDeletedResponse)
async def delete_resource(
    resource_id: str,
    di: Di,
) -> ResourceDeletedResponse:
    return await op_flows_resources_remove(
        ResourceIdPayload(resource_id=resource_id),
        user=require_context().user,
        di=di,
    )

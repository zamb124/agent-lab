"""REST-зеркало каталога NodeConfig: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.realtime.node_operations import (
    op_flows_nodes_catalog_create,
    op_flows_nodes_catalog_item,
    op_flows_nodes_catalog_list,
    op_flows_nodes_catalog_remove,
    op_flows_nodes_catalog_update,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.node_config import (
    NodeConfig,
    NodeDeletedResponse,
    NodeIdPayload,
    NodeListPayload,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(tags=["nodes"])


@router.get("", response_model=OffsetPage[NodeConfig])
@router.get("/", response_model=OffsetPage[NodeConfig])
async def list_nodes(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[NodeConfig]:
    return await op_flows_nodes_catalog_list(
        NodeListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=NodeConfig)
@router.post("/", response_model=NodeConfig)
async def create_node(
    body: NodeConfig,
    container: ContainerDep,
) -> NodeConfig:
    return await op_flows_nodes_catalog_create(
        body,
        user=require_context().user,
        container=container,
    )


@router.get("/{node_id}", response_model=NodeConfig)
async def get_node(
    node_id: str,
    container: ContainerDep,
) -> NodeConfig:
    return await op_flows_nodes_catalog_item(
        NodeIdPayload(node_id=node_id),
        user=require_context().user,
        container=container,
    )


@router.put("/{node_id}", response_model=NodeConfig)
async def update_node(
    node_id: str,
    body: NodeConfig,
    container: ContainerDep,
) -> NodeConfig:
    return await op_flows_nodes_catalog_update(
        body.model_copy(update={"node_id": node_id}),
        user=require_context().user,
        container=container,
    )


@router.delete("/{node_id}", response_model=NodeDeletedResponse)
async def delete_node(
    node_id: str,
    container: ContainerDep,
) -> NodeDeletedResponse:
    return await op_flows_nodes_catalog_remove(
        NodeIdPayload(node_id=node_id),
        user=require_context().user,
        container=container,
    )

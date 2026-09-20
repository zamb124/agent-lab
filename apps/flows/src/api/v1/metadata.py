"""REST-зеркало палитры редактора: тот же `op_*`, что и WS."""

from fastapi import APIRouter

from apps.flows.realtime.operations import (
    FlowsEmptyPayload,
    op_flows_exception_absorb_allow_names,
    op_flows_execution_limits,
    op_flows_node_types,
    op_flows_resource_types,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.flow_api import (
    FlowExecutionLimits,
    FlowNodeTypeCard,
    FlowResourceTypeCard,
)
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(tags=["metadata"])


@router.get("/node-types")
async def get_node_types(container: ContainerDep) -> ListResponse[FlowNodeTypeCard]:
    return await op_flows_node_types(
        FlowsEmptyPayload(), user=require_context().user, container=container
    )


@router.get("/resource-types")
async def get_resource_types(container: ContainerDep) -> ListResponse[FlowResourceTypeCard]:
    return await op_flows_resource_types(
        FlowsEmptyPayload(), user=require_context().user, container=container
    )


@router.get("/exception-absorb-allow-names")
async def get_exception_absorb_allow_names(container: ContainerDep) -> ListResponse[str]:
    return await op_flows_exception_absorb_allow_names(
        FlowsEmptyPayload(), user=require_context().user, container=container
    )


@router.get("/execution-limits")
async def get_execution_limits(container: ContainerDep) -> FlowExecutionLimits:
    return await op_flows_execution_limits(
        FlowsEmptyPayload(), user=require_context().user, container=container
    )

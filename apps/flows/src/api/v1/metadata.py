"""REST-зеркало палитры редактора: тот же `op_*`, что и WS."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    op_flows_exception_absorb_allow_names,
    op_flows_execution_limits,
    op_flows_node_types,
    op_flows_resource_types,
)
from apps.flows.src.models.flow_api import (
    FlowExecutionLimits,
    FlowNodeTypeCard,
    FlowResourceTypeCard,
)
from core.context import require_context
from core.pagination import ListResponse
from core.websocket import EmptyPayload

router = APIRouter(tags=["metadata"])


@router.get("/node-types")
async def get_node_types(di: Di) -> ListResponse[FlowNodeTypeCard]:
    return await op_flows_node_types(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.get("/resource-types")
async def get_resource_types(di: Di) -> ListResponse[FlowResourceTypeCard]:
    return await op_flows_resource_types(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.get("/exception-absorb-allow-names")
async def get_exception_absorb_allow_names(di: Di) -> ListResponse[str]:
    return await op_flows_exception_absorb_allow_names(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.get("/execution-limits")
async def get_execution_limits(di: Di) -> FlowExecutionLimits:
    return await op_flows_execution_limits(
        EmptyPayload(), user=require_context().user, di=di
    )

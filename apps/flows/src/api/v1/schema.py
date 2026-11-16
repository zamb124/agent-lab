"""REST-зеркало JSON Schema контракта flow."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.schema_operations import op_flows_schema
from apps.flows.src.models.flow_api import FlowContractSchema
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(tags=["flows", "schema"])


@router.get("/schema", response_model=FlowContractSchema)
async def get_flow_contract_schema(di: Di) -> FlowContractSchema:
    return await op_flows_schema(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )

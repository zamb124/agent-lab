"""JSON Schema контракта flow для CLI и IDE."""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.realtime.operations import require_company_member
from apps.flows.src.models.flow_api import FlowContractSchema
from apps.flows.src.services.flow_contract_schema import flow_contract_schema
from core.models.identity_models import User
from core.websocket import EmptyPayload


async def op_flows_schema(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> FlowContractSchema:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    return flow_contract_schema()

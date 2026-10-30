"""REST-зеркало Flow UI editor: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.di import Di
from apps.flows.realtime.flow_ui_operations import (
    op_flows_flow_ui_assist,
    op_flows_flow_ui_schema,
    op_flows_flow_ui_templates,
)
from apps.flows.src.flow_ui.templates import FlowUITemplate, FlowUITemplatesPayload
from apps.flows.src.models.flow_ui_assist import FlowUIAssistRequest, FlowUIAssistResult
from core.context import require_context
from core.pagination import OffsetPage
from core.types import JsonObject
from core.websocket import EmptyPayload

router = APIRouter(prefix="/flow-ui", tags=["flows", "flow-ui"])


@router.get("/schema")
async def get_flow_ui_schema(di: Di) -> JsonObject:
    return await op_flows_flow_ui_schema(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )


@router.get("/templates", response_model=OffsetPage[FlowUITemplate])
async def list_flow_ui_templates(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[FlowUITemplate]:
    return await op_flows_flow_ui_templates(
        FlowUITemplatesPayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.post("/assist", response_model=FlowUIAssistResult)
async def assist_flow_ui(
    di: Di, request: FlowUIAssistRequest
) -> FlowUIAssistResult:
    return await op_flows_flow_ui_assist(
        request, user=require_context().user, di=di
    )

"""Flow UI editor: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.realtime.operations import (
    FlowsEmptyPayload,
    require_company_member,
    require_edit_flow,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.flow_ui_assist import (
    FlowUIAssistOutputError,
    FlowUIAssistRequest,
    FlowUIAssistResult,
)
from core.context import require_context
from core.flow_ui.schema import flow_ui_schema
from core.flow_ui.templates import FlowUITemplate, FlowUITemplatesPayload, flow_ui_templates
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.types import JsonObject
from core.websocket import (
    raise_upstream,
)


async def op_flows_flow_ui_schema(
    payload: FlowsEmptyPayload,
    *,
    user: User,
    container: FlowContainer,
) -> JsonObject:
    _ = payload
    _ = user
    _ = await require_company_member(container)
    return flow_ui_schema()


async def op_flows_flow_ui_templates(
    payload: FlowUITemplatesPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[FlowUITemplate]:
    _ = user
    _ = await require_company_member(container)
    templates = flow_ui_templates(require_context().language)
    return OffsetPage[FlowUITemplate](
        items=templates[payload.offset : payload.offset + payload.limit],
        total=len(templates),
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_flow_ui_assist(
    payload: FlowUIAssistRequest,
    *,
    user: User,
    container: FlowContainer,
) -> FlowUIAssistResult:
    _ = user
    _ = await require_edit_flow(container, payload.flow_id)
    try:
        return await container.flow_ui_assist_service.assist(payload)
    except FlowUIAssistOutputError as exc:
        raise_upstream(exc)

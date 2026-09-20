"""Каталог сессий: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.realtime.operations import raise_not_found, require_company_member
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.session_config import (
    SessionConfig,
    SessionDeletedResponse,
    SessionIdPayload,
    SessionListPayload,
)
from core.models.identity_models import User
from core.pagination import OffsetPage


async def op_flows_sessions_list(
    payload: SessionListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[SessionConfig]:
    _ = user
    _ = await require_company_member(container)
    sessions, total = await container.workflow_runtime.search_sessions(
        user_id=payload.user_id,
        flow_id=payload.flow_id,
        branch_id=payload.branch_id,
        date_from=payload.date_from,
        date_to=payload.date_to,
        limit=payload.limit,
        offset=payload.offset,
    )
    return OffsetPage[SessionConfig](
        items=sessions,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_sessions_remove(
    payload: SessionIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> SessionDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    deleted = await container.workflow_runtime.delete_state(payload.session_id)
    if not deleted:
        raise_not_found(LookupError("Session not found"))
    return SessionDeletedResponse(success=True, session_id=payload.session_id)

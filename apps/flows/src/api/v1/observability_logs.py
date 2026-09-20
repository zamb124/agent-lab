"""REST-зеркало Loki logs: path/query → тот же `op_*`, что и WS."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.realtime.observability_operations import (
    op_flows_logs_by_request,
    op_flows_logs_by_session,
    op_flows_logs_by_span,
    op_flows_logs_by_trace,
    op_flows_logs_by_user,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.observability_api import (
    ObservabilityLogsQueryPayload,
    ObservabilityLogsResponse,
)
from core.context import require_context

router = APIRouter(tags=["ObservabilityLogs"])

_MAX_LIMIT = 500
_DEFAULT_LIMIT = 200


@router.get("/by-trace/{trace_id}", response_model=ObservabilityLogsResponse)
async def get_logs_by_trace_id(
    trace_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query()] = None,
    time_to: Annotated[datetime | None, Query()] = None,
) -> ObservabilityLogsResponse:
    return await op_flows_logs_by_trace(
        ObservabilityLogsQueryPayload(
            trace_id=trace_id,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/by-session/{session_id}", response_model=ObservabilityLogsResponse)
async def get_logs_by_session_id(
    session_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query()] = None,
    time_to: Annotated[datetime | None, Query()] = None,
) -> ObservabilityLogsResponse:
    return await op_flows_logs_by_session(
        ObservabilityLogsQueryPayload(
            session_id=session_id,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/by-request/{request_id}", response_model=ObservabilityLogsResponse)
async def get_logs_by_request_id(
    request_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query()] = None,
    time_to: Annotated[datetime | None, Query()] = None,
) -> ObservabilityLogsResponse:
    return await op_flows_logs_by_request(
        ObservabilityLogsQueryPayload(
            request_id=request_id,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/by-span/{span_id}", response_model=ObservabilityLogsResponse)
async def get_logs_by_span_id(
    span_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query()] = None,
    time_to: Annotated[datetime | None, Query()] = None,
) -> ObservabilityLogsResponse:
    return await op_flows_logs_by_span(
        ObservabilityLogsQueryPayload(
            span_id=span_id,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/by-user/{user_id}", response_model=ObservabilityLogsResponse)
async def get_logs_by_user_id(
    user_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query()] = None,
    time_to: Annotated[datetime | None, Query()] = None,
) -> ObservabilityLogsResponse:
    return await op_flows_logs_by_user(
        ObservabilityLogsQueryPayload(
            user_id=user_id,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
        ),
        user=require_context().user,
        container=container,
    )

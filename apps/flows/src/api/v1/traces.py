"""REST-зеркало Tempo/platform_tracing: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.di import Di
from apps.flows.realtime.observability_operations import (
    op_flows_traces_by_session,
    op_flows_traces_by_task,
    op_flows_traces_by_trace,
    op_flows_traces_handoff_chain,
    op_flows_traces_search,
)
from apps.flows.src.models.observability_api import (
    ObservabilityTraceQueryPayload,
    ObservabilityTraceSearchPayload,
    ObservabilityTraceSearchResponse,
    ObservabilityTraceTreeResponse,
)
from core.context import require_context

router = APIRouter(tags=["Traces"])


@router.get("/search", response_model=ObservabilityTraceSearchResponse)
async def search_traces(
    di: Di,
    flow_id: Annotated[str | None, Query()] = None,
    task_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ObservabilityTraceSearchResponse:
    return await op_flows_traces_search(
        ObservabilityTraceSearchPayload(
            flow_id=flow_id,
            task_id=task_id,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/session/{session_id}", response_model=ObservabilityTraceTreeResponse)
async def get_traces_by_session(
    session_id: str,
    di: Di,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ObservabilityTraceTreeResponse:
    return await op_flows_traces_by_session(
        ObservabilityTraceQueryPayload(session_id=session_id, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/task/{task_id}", response_model=ObservabilityTraceTreeResponse)
async def get_traces_by_task(
    task_id: str,
    di: Di,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ObservabilityTraceTreeResponse:
    return await op_flows_traces_by_task(
        ObservabilityTraceQueryPayload(task_id=task_id, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/handoff-chain/{parent_session_id}", response_model=ObservabilityTraceTreeResponse)
async def get_handoff_chain(
    parent_session_id: str,
    di: Di,
) -> ObservabilityTraceTreeResponse:
    return await op_flows_traces_handoff_chain(
        ObservabilityTraceQueryPayload(parent_session_id=parent_session_id),
        user=require_context().user,
        di=di,
    )


@router.get("/trace/{trace_id}", response_model=ObservabilityTraceTreeResponse)
async def get_trace(
    trace_id: str,
    di: Di,
) -> ObservabilityTraceTreeResponse:
    return await op_flows_traces_by_trace(
        ObservabilityTraceQueryPayload(trace_id=trace_id),
        user=require_context().user,
        di=di,
    )

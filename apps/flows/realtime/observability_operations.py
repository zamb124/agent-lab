"""Loki logs и Tempo traces: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Never

from apps.flows.di import Di
from apps.flows.src.models.observability_api import (
    ObservabilityLogsQueryPayload,
    ObservabilityLogsResponse,
    ObservabilityTraceQueryPayload,
    ObservabilityTraceSearchPayload,
    ObservabilityTraceSearchResponse,
    ObservabilityTraceTreeResponse,
)
from core.clients.loki_client import LokiClient, LokiClientError, LokiLogEntry
from core.clients.tempo_client import TempoClientError
from core.models.identity_models import User
from core.tracing.models import Span
from core.tracing.span_tree import build_span_tree
from core.types import JsonObject
from core.websocket import (
    raise_invalid,
    raise_not_found,
    raise_unavailable,
)

_ATTR_SESSION_AGENT = "platform.session.agent"
_ATTR_TASK_ID = "platform.task_id"
_LOKI_UNCONFIGURED = (
    "Loki query API не настроен: задайте logging.loki_query_url "
    "или logging.loki_url (push; база для query берётся из scheme://netloc)"
)


def raise_observability(exc: Exception) -> Never:
    if isinstance(exc, LokiClientError | TempoClientError):
        raise_unavailable(exc)
    raise_invalid(exc)


async def _run_loki(awaitable: Awaitable[list[LokiLogEntry]]) -> list[LokiLogEntry]:
    try:
        return await awaitable
    except LokiClientError as exc:
        raise_observability(exc)


async def _tempo_spans(awaitable: Awaitable[list[JsonObject]]) -> list[JsonObject]:
    try:
        return await awaitable
    except TempoClientError as exc:
        raise_observability(exc)


async def _tempo_trace_ids(awaitable: Awaitable[list[str]]) -> list[str]:
    try:
        return await awaitable
    except TempoClientError as exc:
        raise_observability(exc)


def _require_loki(di: Di) -> LokiClient:
    client = di.loki_client
    if not client.is_configured:
        raise_unavailable(RuntimeError(_LOKI_UNCONFIGURED))
    return client


def _require_lookup(value: str, field: str) -> str:
    if value == "":
        raise_invalid(ValueError(f"{field} required"))
    return value


def _logs_response(
    entries: list[LokiLogEntry],
    *,
    trace_id: str = "",
    session_id: str = "",
    request_id: str = "",
    span_id: str = "",
    user_id: str = "",
) -> ObservabilityLogsResponse:
    return ObservabilityLogsResponse(
        count=len(entries),
        entries=entries,
        trace_id=trace_id,
        session_id=session_id,
        request_id=request_id,
        span_id=span_id,
        user_id=user_id,
    )


def _append_unique_span(
    all_spans: list[JsonObject],
    seen_span_ids: set[str],
    span: JsonObject,
) -> None:
    sid = span.get("span_id", "")
    if isinstance(sid, str) and sid != "" and sid not in seen_span_ids:
        seen_span_ids.add(sid)
        all_spans.append(span)


async def _spans_for_trace_ids(
    di: Di,
    trace_ids: list[str],
) -> list[JsonObject]:
    all_spans: list[JsonObject] = []
    seen_span_ids: set[str] = set()
    for tid in trace_ids:
        spans = await _tempo_spans(di.tempo_client.get_trace(tid))
        for span in spans:
            _append_unique_span(all_spans, seen_span_ids, span)
    return all_spans


def _tree_response(
    spans: list[JsonObject],
    *,
    session_id: str = "",
    task_id: str = "",
    trace_id: str = "",
    parent_session_id: str = "",
    handoff_depth: int | None = None,
) -> ObservabilityTraceTreeResponse:
    return ObservabilityTraceTreeResponse(
        spans_count=len(spans),
        spans=build_span_tree(spans),
        session_id=session_id,
        task_id=task_id,
        trace_id=trace_id,
        parent_session_id=parent_session_id,
        handoff_depth=handoff_depth,
    )


async def op_flows_logs_by_trace(
    payload: ObservabilityLogsQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityLogsResponse:
    _ = user
    trace_id = _require_lookup(payload.trace_id, "trace_id")
    loki = _require_loki(di)
    entries = await _run_loki(
        loki.query_by_trace_id(
            trace_id,
            time_from=payload.time_from,
            time_to=payload.time_to,
            limit=payload.limit,
        )
    )
    return _logs_response(entries, trace_id=trace_id)


async def op_flows_logs_by_session(
    payload: ObservabilityLogsQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityLogsResponse:
    _ = user
    session_id = _require_lookup(payload.session_id, "session_id")
    loki = _require_loki(di)
    entries = await _run_loki(
        loki.query_by_session_id(
            session_id,
            time_from=payload.time_from,
            time_to=payload.time_to,
            limit=payload.limit,
        )
    )
    return _logs_response(entries, session_id=session_id)


async def op_flows_logs_by_request(
    payload: ObservabilityLogsQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityLogsResponse:
    _ = user
    request_id = _require_lookup(payload.request_id, "request_id")
    loki = _require_loki(di)
    entries = await _run_loki(
        loki.query_by_request_id(
            request_id,
            time_from=payload.time_from,
            time_to=payload.time_to,
            limit=payload.limit,
        )
    )
    return _logs_response(entries, request_id=request_id)


async def op_flows_logs_by_span(
    payload: ObservabilityLogsQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityLogsResponse:
    _ = user
    span_id = _require_lookup(payload.span_id, "span_id")
    loki = _require_loki(di)
    entries = await _run_loki(
        loki.query_by_span_id(
            span_id,
            time_from=payload.time_from,
            time_to=payload.time_to,
            limit=payload.limit,
        )
    )
    return _logs_response(entries, span_id=span_id)


async def op_flows_logs_by_user(
    payload: ObservabilityLogsQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityLogsResponse:
    _ = user
    user_id = _require_lookup(payload.user_id, "user_id")
    loki = _require_loki(di)
    entries = await _run_loki(
        loki.query_by_user_id(
            user_id,
            time_from=payload.time_from,
            time_to=payload.time_to,
            limit=payload.limit,
        )
    )
    return _logs_response(entries, user_id=user_id)


async def op_flows_traces_search(
    payload: ObservabilityTraceSearchPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityTraceSearchResponse:
    _ = user
    _ = di
    traces, total = await Span.search_traces(
        flow_id=payload.flow_id,
        task_id=payload.task_id,
        limit=payload.limit,
        offset=payload.offset,
    )
    return ObservabilityTraceSearchResponse(traces_count=total, traces=traces)


async def op_flows_traces_by_session(
    payload: ObservabilityTraceQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityTraceTreeResponse:
    _ = user
    session_id = _require_lookup(payload.session_id, "session_id")
    raw_ids = await _tempo_trace_ids(
        di.tempo_client.search_trace_ids_by_attribute(
            _ATTR_SESSION_AGENT, session_id, limit=payload.limit
        )
    )
    spans = await _spans_for_trace_ids(di, raw_ids)
    return _tree_response(spans, session_id=session_id)


async def op_flows_traces_by_task(
    payload: ObservabilityTraceQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityTraceTreeResponse:
    _ = user
    task_id = _require_lookup(payload.task_id, "task_id")
    raw_ids = await _tempo_trace_ids(
        di.tempo_client.search_trace_ids_by_attribute(
            _ATTR_TASK_ID, task_id, limit=payload.limit
        )
    )
    spans = await _spans_for_trace_ids(di, raw_ids)
    return _tree_response(spans, task_id=task_id)


async def op_flows_traces_by_trace(
    payload: ObservabilityTraceQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityTraceTreeResponse:
    _ = user
    trace_id = _require_lookup(payload.trace_id, "trace_id")
    spans = await _tempo_spans(di.tempo_client.get_trace(trace_id))
    return _tree_response(spans, trace_id=trace_id)


async def op_flows_traces_handoff_chain(
    payload: ObservabilityTraceQueryPayload,
    *,
    user: User,
    di: Di,
) -> ObservabilityTraceTreeResponse:
    _ = user
    parent_session_id = _require_lookup(payload.parent_session_id, "parent_session_id")
    parent_state = await di.workflow_runtime.get_state(parent_session_id)
    if parent_state is None:
        raise_not_found(LookupError("parent session not found"))
    trace_id = parent_state.handoff_trace_id
    if trace_id is None:
        raise_not_found(LookupError("handoff_trace_id not set on parent session"))
    tempo_spans = await _tempo_spans(di.tempo_client.get_trace(trace_id))
    db_spans = await Span.list_for_trace(trace_id)
    all_spans: list[JsonObject] = []
    seen: set[str] = set()
    for span in tempo_spans:
        _append_unique_span(all_spans, seen, span)
    for span_record in db_spans:
        if span_record.span_id not in seen:
            seen.add(span_record.span_id)
            all_spans.append(span_record.to_json_object())
    return _tree_response(
        all_spans,
        parent_session_id=parent_session_id,
        trace_id=trace_id,
        handoff_depth=parent_state.handoff_depth,
    )

"""
Handoff trace propagation: fork/continue TraceContext и атрибуты spans.
"""

from __future__ import annotations

import core.tracing.attributes as attr
from core.tracing.context import TraceContext, get_current_trace_context
from core.tracing.provider import is_tracing_enabled
from core.tracing.tracer import get_tracer
from core.types import JsonObject, OtelAttributes, OtelAttributeValue

HANDOFF_OP_INITIATED = "flows.handoff.initiated"
HANDOFF_OP_ROUTE_REPLY = "flows.handoff.route_reply"
HANDBACK_OP_COMPLETED = "flows.handback.completed"
HANDOFF_OP_EXTERNAL = "flows.handoff.external"


def resolve_active_trace_context() -> TraceContext | None:
    if not is_tracing_enabled():
        return None
    raw = get_current_trace_context()
    if raw is not None:
        return TraceContext.from_dict(raw)
    return get_tracer().get_current_trace_context()


def fork_handoff_trace_context(
    base: TraceContext,
    *,
    session_agent: str | None = None,
    flow_id: str | None = None,
    branch_id: str | None = None,
    task_id: str | None = None,
    context_id: str | None = None,
    channel: str | None = None,
    is_resume: bool | None = None,
) -> TraceContext:
    forked = get_tracer().fork_trace_context(base)
    if session_agent is not None:
        forked = TraceContext.merge_from(forked, session_agent=session_agent)
    if flow_id is not None:
        forked = TraceContext.merge_from(forked, flow_id=flow_id)
    if branch_id is not None:
        forked = TraceContext.merge_from(forked, branch_id=branch_id)
    if task_id is not None:
        forked = TraceContext.merge_from(forked, task_id=task_id)
    if context_id is not None:
        forked = TraceContext.merge_from(forked, context_id=context_id)
    if channel is not None:
        forked = TraceContext.merge_from(forked, channel=channel)
    if is_resume is not None:
        forked = TraceContext.merge_from(forked, is_resume=is_resume)
    return forked


def continue_handoff_trace_context(
    trace_id: str,
    *,
    parent_span_id: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    user_groups: list[str] | None = None,
    session_auth: str | None = None,
    session_agent: str | None = None,
    task_id: str | None = None,
    context_id: str | None = None,
    flow_id: str | None = None,
    branch_id: str | None = None,
    channel: str | None = None,
    is_resume: bool = False,
) -> TraceContext:
    return get_tracer().continue_trace_context(
        trace_id,
        parent_span_id=parent_span_id,
        user_id=user_id,
        user_name=user_name,
        user_groups=user_groups,
        session_auth=session_auth,
        session_agent=session_agent,
        task_id=task_id,
        context_id=context_id,
        flow_id=flow_id,
        branch_id=branch_id,
        channel=channel,
        is_resume=is_resume,
    )


def handoff_span_attributes(
    *,
    phase: str,
    parent_session_id: str,
    child_session_id: str | None = None,
    target_flow_id: str | None = None,
    depth: int | None = None,
    trace_id: str | None = None,
) -> OtelAttributes:
    attrs: dict[str, OtelAttributeValue] = {
        attr.ATTR_HANDOFF_PHASE: phase,
        attr.ATTR_HANDOFF_PARENT_SESSION_ID: parent_session_id,
    }
    if child_session_id is not None:
        attrs[attr.ATTR_HANDOFF_CHILD_SESSION_ID] = child_session_id
    if target_flow_id is not None:
        attrs[attr.ATTR_HANDOFF_TARGET_FLOW_ID] = target_flow_id
    if depth is not None:
        attrs[attr.ATTR_HANDOFF_DEPTH] = depth
    if trace_id is not None:
        attrs[attr.ATTR_HANDOFF_TRACE_ID] = trace_id
    return attrs


def trace_context_to_kiq_payload(trace_ctx: TraceContext) -> JsonObject:
    return trace_ctx.to_dict()

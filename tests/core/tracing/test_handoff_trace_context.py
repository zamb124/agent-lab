"""Unit tests for handoff trace context fork/continue."""

from __future__ import annotations

import pytest

from core.tracing.context import TraceContext
from core.tracing.tracer import get_tracer


@pytest.mark.asyncio
async def test_fork_trace_context_preserves_trace_id() -> None:
    tracer = get_tracer()
    base = tracer.create_trace_context(
        user_id="u1",
        session_agent="parent:ctx",
        flow_id="parent_flow",
    )
    forked = tracer.fork_trace_context(
        base,
        session_agent="child:ctx",
        flow_id="child_flow",
        is_resume=False,
    )
    assert forked.trace_id == base.trace_id
    assert forked.span_id != base.span_id
    assert forked.parent_span_id == base.span_id
    assert forked.session_agent == "child:ctx"
    assert forked.flow_id == "child_flow"


@pytest.mark.asyncio
async def test_continue_trace_context_keeps_trace_id() -> None:
    tracer = get_tracer()
    continued = tracer.continue_trace_context(
        "abc123trace",
        user_id="u1",
        session_agent="child:ctx",
        flow_id="child_flow",
    )
    assert continued.trace_id == "abc123trace"
    assert continued.span_id
    assert continued.flow_id == "child_flow"


def test_trace_context_merge_from() -> None:
    base = TraceContext(
        trace_id="t1",
        span_id="s1",
        flow_id="f1",
    )
    merged = TraceContext.merge_from(base, flow_id="f2", is_resume=True)
    assert merged.trace_id == "t1"
    assert merged.flow_id == "f2"
    assert merged.is_resume is True

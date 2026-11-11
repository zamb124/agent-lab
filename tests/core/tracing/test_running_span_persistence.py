"""Горячие спаны: строка RUNNING при открытии, финальный upsert при закрытии."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import core.tracing.attributes as trace_attributes
from core.tracing import setup_tracing
from core.tracing.config import TracingConfig
from core.tracing.models import Span, TraceSpanEvent
from core.tracing.operation_span import traced_operation
from core.tracing.provider import set_tracing_enabled
from core.tracing.tracer import set_tracing_service_name


def _enable_tracing(svc: str) -> None:
    config = TracingConfig(
        enabled=True,
        postgres_enabled=True,
        tempo_enabled=False,
        service_name="platform-test",
    )
    setup_tracing(config)
    set_tracing_service_name(svc)
    set_tracing_enabled(True)


@pytest.mark.asyncio
async def test_traced_operation_writes_running_row_then_final_row(
    unique_id: str,
) -> None:
    svc = f"trace_running_{unique_id}"
    op = f"sync.test.running_{unique_id}"
    _enable_tracing(svc)

    async with traced_operation(
        op,
        event_type="test.worker",
        operation_category="sync_command",
    ):
        rows, _ = await Span.span_page_and_cursor_for_service_by_start_time_and_span_id_desc(
            service_name=svc,
            operation_name=op,
            limit=10,
        )
        assert len(rows) == 1
        running = rows[0]
        assert running.status == "RUNNING"
        assert running.end_time is None
        assert running.duration_ms is None

    rows, _ = await Span.span_page_and_cursor_for_service_by_start_time_and_span_id_desc(
        service_name=svc,
        operation_name=op,
        limit=10,
    )
    assert len(rows) == 1
    final = rows[0]
    assert final.span_id == running.span_id
    assert final.status == "OK"
    assert final.end_time is not None
    assert final.duration_ms is not None
    assert final.duration_ms >= 0


@pytest.mark.asyncio
async def test_upsert_span_updates_existing_row_in_place(
    unique_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    span_id = f"upsert-{unique_id}"
    trace_id = f"trace-{unique_id}"
    running = Span(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation_name="files.read.parse",
        kind="INTERNAL",
        start_time=now,
        end_time=None,
        duration_ms=None,
        status="RUNNING",
        status_message=None,
        service_name="capability_gateway",
        company_id="system",
        namespace="default",
        user_id="user1",
        user_name=None,
        user_groups=None,
        session_auth=None,
        session_agent=f"session-{unique_id}",
        channel=None,
        event_type="capability.call",
        resource_type="flow",
        resource_id="flow1",
        attributes={},
        events=[],
    )
    await Span.upsert_span(running)

    finished = running.model_copy(
        update={
            "operation_name": "files.read.parse.final",
            "end_time": now,
            "duration_ms": 7,
            "status": "OK",
            "attributes": {"platform.files.stage": "parse"},
            "events": [
                TraceSpanEvent(
                    name="cache.hit",
                    timestamp="2026-01-01T00:00:00+00:00",
                    attributes={"nested": {"page": {"index": 1, "blocks": ["a", "b"]}}},
                )
            ],
        }
    )
    await Span.upsert_span(finished)

    rows = await Span.list_for_trace_by_start_time_asc(trace_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.operation_name == "files.read.parse.final"
    assert row.status == "OK"
    assert row.end_time is not None
    assert row.duration_ms == 7
    assert row.attributes["platform.files.stage"] == "parse"
    assert row.events[0].attributes["nested"] == {
        "page": {"index": 1, "blocks": ["a", "b"]}
    }


@pytest.mark.asyncio
async def test_upsert_span_requires_service_name(unique_id: str) -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        await Span.upsert_span(
            Span(
                span_id=f"bad-{unique_id}",
                trace_id=f"trace-{unique_id}",
                parent_span_id=None,
                operation_name="x",
                kind="INTERNAL",
                start_time=now,
                end_time=None,
                duration_ms=None,
                status="RUNNING",
                status_message=None,
                service_name="",
                company_id=None,
                namespace=None,
                user_id=None,
                user_name=None,
                user_groups=None,
                session_auth=None,
                session_agent=None,
                channel=None,
                event_type=None,
                resource_type=None,
                resource_id=None,
                attributes={},
                events=[],
            )
        )


@pytest.mark.asyncio
async def test_traced_operation_session_agent_from_attributes(
    unique_id: str,
) -> None:
    """session_agent из platform-атрибутов спана — колонка заполняется без trace_ctx."""
    svc = f"trace_sess_{unique_id}"
    op = f"sync.test.session_{unique_id}"
    session_agent = f"flow:{unique_id}"
    _enable_tracing(svc)

    async with traced_operation(
        op,
        event_type="test.worker",
        operation_category="sync_command",
        extra_attributes={trace_attributes.ATTR_SESSION_AGENT: session_agent},
    ):
        rows = await Span.list_by_session_agent_desc(session_agent, limit=10)
        assert len(rows) == 1
        assert rows[0].status == "RUNNING"
        assert rows[0].session_agent == session_agent

    rows = await Span.list_by_session_agent_desc(session_agent, limit=10)
    assert len(rows) == 1
    assert rows[0].status == "OK"

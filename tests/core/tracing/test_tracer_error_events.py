"""Проверки сохранения подробных ошибок в spans."""

from __future__ import annotations

import pytest

import core.tracing.attributes as trace_attr
from core.tracing import get_tracer


@pytest.mark.asyncio
async def test_platform_tracer_persists_exception_event(app, container, unique_id: str):
    """Exception внутри span должен быть виден разработчику агента в platform_tracing."""
    _ = app
    operation_name = f"test.error_span.{unique_id}"
    tracer = get_tracer()

    with pytest.raises(RuntimeError, match="agent-visible boom"):
        async with tracer.platform_operation_span(operation_name):
            raise RuntimeError("agent-visible boom")

    spans, _ = await container.span_repository.list_spans_for_service(
        service_name="flows",
        operation_name=operation_name,
        limit=10,
    )

    assert len(spans) == 1
    span = spans[0]
    assert span["status"] == "ERROR"
    assert "agent-visible boom" in (span["status_message"] or "")
    assert span["attributes"][trace_attr.ATTR_ERROR_TYPE] == "RuntimeError"
    assert span["attributes"][trace_attr.ATTR_ERROR_MESSAGE] == "agent-visible boom"

    exception_events = [event for event in span["events"] if event["name"] == "exception"]
    assert exception_events
    event_attrs = exception_events[0]["attributes"]
    assert event_attrs["exception.type"] == "RuntimeError"
    assert event_attrs["exception.message"] == "agent-visible boom"
    assert "test_platform_tracer_persists_exception_event" in event_attrs["exception.stacktrace"]


@pytest.mark.asyncio
async def test_platform_tracer_does_not_mark_flow_interrupt_as_error(
    app, container, unique_id: str
):
    """FlowInterrupt — штатная пауза flow, а не ошибка для разработчика агента."""
    from apps.flows.src.runtime.exceptions import FlowInterrupt

    _ = app
    operation_name = f"test.control_flow_span.{unique_id}"
    tracer = get_tracer()

    with pytest.raises(FlowInterrupt):
        async with tracer.platform_operation_span(operation_name):
            raise FlowInterrupt(question="Нужен ввод")

    spans, _ = await container.span_repository.list_spans_for_service(
        service_name="flows",
        operation_name=operation_name,
        limit=10,
    )

    assert len(spans) == 1
    span = spans[0]
    assert span["status"] == "OK"
    assert trace_attr.ATTR_ERROR_TYPE not in span["attributes"]
    assert [event for event in span["events"] if event["name"] == "exception"] == []

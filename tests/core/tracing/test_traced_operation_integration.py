"""
Интеграция traced_operation с SpanRepository: колонки и атрибуты без HTTP-контекста.
"""

from __future__ import annotations

import pytest

import core.tracing.attributes as trace_attributes
from core.tracing import setup_tracing
from core.tracing.config import TracingConfig
from core.tracing.operation_span import traced_operation
from core.tracing.provider import set_tracing_enabled
from core.tracing.tracer import set_span_repository, set_tracing_service_name


@pytest.mark.asyncio
async def test_traced_operation_persists_company_id_from_span_attributes(
    container,
    unique_id: str,
) -> None:
    svc = f"trace_op_test_{unique_id}"
    op = f"sync.test.worker_span_{unique_id}"
    company = f"company_{unique_id}"

    config = TracingConfig(
        enabled=True,
        postgres_enabled=True,
        tempo_enabled=False,
        service_name="platform-test",
    )
    setup_tracing(config)
    set_tracing_service_name(svc)
    set_span_repository(container.span_repository)
    set_tracing_enabled(True)

    async with traced_operation(
        op,
        event_type="test.worker",
        operation_category="sync_command",
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company,
            trace_attributes.ATTR_TENANT_NAMESPACE: "ns_test",
        },
    ):
        pass

    rows, _ = await container.span_repository.list_spans_for_service(
        service_name=svc,
        operation_name=op,
        limit=10,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["operation_name"] == op
    assert row["company_id"] == company
    assert row["namespace"] == "ns_test"
    attrs = row.get("attributes") or {}
    assert attrs.get(trace_attributes.ATTR_TENANT_COMPANY_ID) == company

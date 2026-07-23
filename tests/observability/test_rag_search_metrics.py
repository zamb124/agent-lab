"""Runtime tests: RAG search and rerank operation_finished logs."""

from __future__ import annotations

import pytest

import core.tracing.attributes as trace_attr
from core.tracing.operation_span import traced_operation
from tests.fixtures.observability_log_capture import (
    find_caplog_record,
    require_log_fields,
    require_numeric_field,
)
from tests.observability.contracts import RAG_SEARCH_FINISHED

pytestmark = pytest.mark.timeout(30)


@pytest.mark.asyncio
async def test_rag_search_namespace_operation_finished(
    enable_observability_tracing: None,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    namespace_id = f"rag-ns-{unique_id}"
    async with traced_operation(
        "rag.search.namespace",
        event_type="rag.search",
        operation_category="rag_search",
        resource_type="rag.namespace",
        resource_id=namespace_id,
        extra_attributes={
            trace_attr.ATTR_RAG_STAGE: "search",
            "platform.rag.search_pool_size": 5,
        },
    ):
        pass

    rec = find_caplog_record(
        observability_caplog,
        message=RAG_SEARCH_FINISHED.message,
        logger_name="core.tracing.operation_log_mirror",
    )
    fields = require_log_fields(
        rec,
        required={
            "operation_name": str,
            "operation_status": str,
            "operation_duration_ms": (int, float),
        },
    )
    assert fields["operation_name"] == "rag.search.namespace"
    assert fields["operation_status"] == "ok"
    require_numeric_field(fields, "operation_duration_ms", min_value=0.0)


@pytest.mark.asyncio
async def test_rag_rerank_after_retrieve_operation_finished(
    enable_observability_tracing: None,
    observability_caplog: pytest.LogCaptureFixture,
) -> None:
    async with traced_operation(
        "rag.rerank.after_retrieve",
        event_type="rag.rerank",
        operation_category="rag_rerank",
        extra_attributes={
            trace_attr.ATTR_RAG_STAGE: "rerank",
            "platform.rag.rerank_pool_size": 0,
        },
    ):
        pass

    rec = find_caplog_record(
        observability_caplog,
        message=RAG_SEARCH_FINISHED.message,
        logger_name="core.tracing.operation_log_mirror",
    )
    fields = require_log_fields(
        rec,
        required={
            "operation_name": str,
            "operation_status": str,
        },
    )
    assert fields["operation_name"] == "rag.rerank.after_retrieve"
    assert fields["operation_status"] == "ok"

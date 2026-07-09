"""Runtime tests: generic operation_finished log-mirror via traced_operation."""

from __future__ import annotations

import pytest

import core.tracing.attributes as trace_attr
from core.logging.attributes import LOG_OPERATION_DURATION_MS, LOG_OPERATION_NAME, LOG_OPERATION_STATUS
from core.tracing.operation_span import traced_operation
from tests.fixtures.observability_log_capture import (
    find_caplog_record,
    require_log_fields,
    require_numeric_field,
)
from tests.observability.contracts import OPERATION_FINISHED

pytestmark = pytest.mark.timeout(30)


@pytest.mark.asyncio
async def test_operation_finished_emitted_for_traced_operation_with_mirror_always(
    enable_observability_tracing: None,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    operation_name = f"test.observability.probe.{unique_id}"
    async with traced_operation(
        operation_name,
        operation_category="test_observability",
        extra_attributes={
            trace_attr.ATTR_OPERATION_LOG_MIRROR: "always",
        },
    ):
        pass

    rec = find_caplog_record(
        observability_caplog,
        message=OPERATION_FINISHED.message,
        logger_name="core.tracing.operation_log_mirror",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_OPERATION_NAME: str,
            LOG_OPERATION_STATUS: str,
            LOG_OPERATION_DURATION_MS: (int, float),
        },
    )
    assert fields[LOG_OPERATION_NAME] == operation_name
    assert fields[LOG_OPERATION_STATUS] == "ok"
    require_numeric_field(fields, LOG_OPERATION_DURATION_MS, min_value=0.0)

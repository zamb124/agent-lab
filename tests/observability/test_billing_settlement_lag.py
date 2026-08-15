"""Runtime tests: billing settlement lag completion log."""


from __future__ import annotations

from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401
from datetime import datetime, timedelta, timezone

import pytest

import core.tracing.attributes as trace_attr
from apps.idle_worker.tasks.span_billing_settlement_tasks import span_billing_settlement_tick
from core.logging.attributes import LOG_BILLING_SETTLEMENT_LAG_MS, LOG_OPERATION_NAME
from core.models.billing_models import UsageType
from core.models.identity_models import Company
from core.tracing.models import TraceSpanWrite
from tests.fixtures.observability_log_capture import (
    require_log_fields,
    require_numeric_field,
    wait_for_caplog_event,
)
from tests.observability.contracts import BILLING_SETTLEMENT_LAG

pytestmark = pytest.mark.timeout(60)


@pytest.mark.asyncio
async def test_billing_settlement_lag_emitted_for_pending_span(
    frontend_container,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
    system_user_id: str,
) -> None:
    cid = f"bill-lag-{unique_id}"
    company = Company(
        company_id=cid,
        name="Billing lag test",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=5000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    repo = frontend_container.span_repository
    sid = f"span-lag-{unique_id}"
    ended_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    started_at = ended_at - timedelta(seconds=1)
    await repo.save_span(
        TraceSpanWrite(
            span_id=sid,
            trace_id=f"trace-lag-{unique_id}",
            parent_span_id=None,
            operation_name=f"bill.lag.{unique_id}",
            kind="INTERNAL",
            start_time=started_at,
            end_time=ended_at,
            duration_ms=1000,
            status="OK",
            service_name="flows_worker",
            company_id=cid,
            namespace="default",
            user_id=system_user_id,
            user_name=None,
            user_groups=None,
            session_auth=None,
            session_agent=None,
            channel=None,
            event_type=None,
            resource_type=None,
            resource_id=None,
            attributes={
                trace_attr.ATTR_BILLING_RESOURCE_NAME: "llm:*",
                trace_attr.ATTR_BILLING_PENDING_SETTLEMENT: True,
                trace_attr.ATTR_BILLING_USAGE_TYPE: UsageType.LLM_REQUEST.value,
                trace_attr.ATTR_BILLING_QUANTITY: 1,
            },
            events=[],
        )
    )

    _ = await span_billing_settlement_tick(company_id=cid)

    expected_operation_name = f"bill.lag.{unique_id}"
    rec = await wait_for_caplog_event(
        observability_caplog,
        message=BILLING_SETTLEMENT_LAG.message,
        logger_name="apps.idle_worker.tasks.span_billing_settlement_tasks",
        predicate=lambda fields: fields.get(LOG_OPERATION_NAME) == expected_operation_name,
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_BILLING_SETTLEMENT_LAG_MS: (int, float),
            LOG_OPERATION_NAME: str,
        },
    )
    assert fields[LOG_OPERATION_NAME] == expected_operation_name
    require_numeric_field(fields, LOG_BILLING_SETTLEMENT_LAG_MS, min_value=0.0)

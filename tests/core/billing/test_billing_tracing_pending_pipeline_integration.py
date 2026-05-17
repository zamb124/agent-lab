"""
Трейсинг: spans с pending settlement -> list_spans_pending_billing_settlement -> BillingService.
Реальная БД platform_tracing и shared storage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import core.tracing.attributes as trace_attr
from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
)
from core.billing.span_billing_settlement import SpanBillingSettlement

pytestmark = pytest.mark.xdist_group("billing_global_resource_base_prices_json")


@pytest.mark.asyncio
async def test_list_spans_pending_billing_limit_invalid(frontend_container) -> None:
    repo = frontend_container.span_repository
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="limit"):
        await repo.list_spans_pending_billing_settlement(
            from_time=now - timedelta(hours=1),
            to_time=now,
            limit=0,
        )


@pytest.mark.asyncio
async def test_list_spans_pending_billing_naive_datetime_raises(frontend_container) -> None:
    repo = frontend_container.span_repository
    now = datetime.now(timezone.utc)
    naive = datetime.now()
    with pytest.raises(ValueError, match="timezone"):
        await repo.list_spans_pending_billing_settlement(
            from_time=naive,
            to_time=now,
            limit=10,
        )


@pytest.mark.asyncio
async def test_save_pending_span_list_then_legacy_settle_creates_usage(
    frontend_container, unique_id: str, system_user_id: str
) -> None:
    from core.models.identity_models import Company

    cid = f"trpipe_{unique_id}"
    company = Company(
        company_id=cid,
        name="Trace pipe",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=5000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    repo = frontend_container.span_repository
    sid = f"pend_{unique_id}"
    tid = f"tr_{unique_id}"
    t0 = datetime.now(timezone.utc)
    await repo.save_span(
        {
            "span_id": sid,
            "trace_id": tid,
            "parent_span_id": None,
            "operation_name": f"bill.pipe.{unique_id}",
            "kind": "INTERNAL",
            "start_time": t0,
            "end_time": t0,
            "duration_ms": 0,
            "status": "OK",
            "service_name": f"svc_{unique_id}",
            "company_id": cid,
            "namespace": "default",
            "user_id": system_user_id,
            "user_name": None,
            "user_groups": None,
            "session_auth": None,
            "session_agent": None,
            "channel": None,
            "event_type": None,
            "resource_type": None,
            "resource_id": None,
            "attributes": {
                trace_attr.ATTR_BILLING_RESOURCE_NAME: "llm:*",
                trace_attr.ATTR_BILLING_PENDING_SETTLEMENT: True,
                trace_attr.ATTR_BILLING_USAGE_TYPE: "llm_request",
                trace_attr.ATTR_BILLING_QUANTITY: 2,
            },
            "events": [],
        }
    )

    from_time = t0 - timedelta(seconds=30)
    to_time = t0 + timedelta(seconds=30)
    pending = await repo.list_spans_pending_billing_settlement(
        from_time=from_time,
        to_time=to_time,
        limit=50,
    )
    ours = [p for p in pending if p["span_id"] == sid]
    assert len(ours) == 1
    span_dict = ours[0]
    assert span_dict["attributes"][trace_attr.ATTR_BILLING_RESOURCE_NAME] == "llm:*"

    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service
    rules_doc = SettlementRulesDocument()

    n = await billing.settle_pending_span_in_job(
        span_dict=span_dict,
        settlement=settlement,
        fallback_user_id="",
        rules_doc=rules_doc,
    )
    assert n == 1

    n2 = await billing.settle_pending_span_in_job(
        span_dict=span_dict,
        settlement=settlement,
        fallback_user_id="",
        rules_doc=rules_doc,
    )
    assert n2 == 0

    recs = await frontend_container.usage_repository.admin_search_usage_records(
        company_id=cid, limit=20
    )
    matched = [r for r in recs if r.metadata.get("span_id") == sid]
    assert len(matched) == 1
    assert matched[0].quantity == 2


@pytest.mark.asyncio
async def test_pending_span_rules_engine_quantity_from_attr(
    frontend_container, unique_id: str, system_user_id: str
) -> None:
    from core.models.identity_models import Company

    cid = f"trrule_{unique_id}"
    company = Company(
        company_id=cid,
        name="Trace rules",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=5000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    key = f"billing:company:{cid}:resource_base_prices_json"
    await frontend_container.shared_storage.set(
        key,
        '{"llm": {"*": 0.5}}',
        force_global=True,
    )

    repo = frontend_container.span_repository
    sid = f"qr_{unique_id}"
    tid = f"trr_{unique_id}"
    t0 = datetime.now(timezone.utc)
    tok_key = "platform.llm.input_tokens"
    await repo.save_span(
        {
            "span_id": sid,
            "trace_id": tid,
            "parent_span_id": None,
            "operation_name": f"qty.{unique_id}.run",
            "kind": "INTERNAL",
            "start_time": t0,
            "end_time": t0,
            "duration_ms": 0,
            "status": "OK",
            "service_name": "flows",
            "company_id": cid,
            "namespace": "default",
            "user_id": system_user_id,
            "user_name": None,
            "user_groups": None,
            "session_auth": None,
            "session_agent": None,
            "channel": None,
            "event_type": None,
            "resource_type": None,
            "resource_id": None,
            "attributes": {
                trace_attr.ATTR_BILLING_RESOURCE_NAME: "llm:*",
                trace_attr.ATTR_BILLING_PENDING_SETTLEMENT: True,
                tok_key: 100,
            },
            "events": [],
        }
    )

    from_time = t0 - timedelta(seconds=30)
    to_time = t0 + timedelta(seconds=30)
    pending = await repo.list_spans_pending_billing_settlement(
        from_time=from_time,
        to_time=to_time,
        limit=50,
    )
    span_dict = next(p for p in pending if p["span_id"] == sid)

    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.ALL_MATCHING,
        rules=[
            SettlementRule(
                rule_id=f"tok_rule_{unique_id}",
                priority=1,
                resource_name="llm:*",
                usage_type="llm_request",
                quantity_from=f"attr:{tok_key}",
                match=SettlementRuleMatch(operation_name_prefix=f"qty.{unique_id}."),
            ),
        ],
    )
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service
    n = await billing.settle_pending_span_in_job(
        span_dict=span_dict,
        settlement=settlement,
        fallback_user_id="",
        rules_doc=doc,
    )
    assert n == 1

    recs = await frontend_container.usage_repository.admin_search_usage_records(
        company_id=cid, limit=20
    )
    matched = [r for r in recs if r.metadata.get("rule_id") == f"tok_rule_{unique_id}"]
    assert len(matched) == 1
    assert matched[0].quantity == 100

    await frontend_container.shared_storage.delete(key, force_global=True)

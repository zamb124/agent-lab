"""
Интеграция: составной ключ settlement, правила, per-company прайс (реальные репозитории и storage).
"""

from __future__ import annotations

import json

import pytest

from core.billing.service import company_resource_prices_storage_key
from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
)
from core.billing.span_billing_settlement import SpanBillingSettlement
from core.models.billing_models import DEFAULT_TARIFF_PRICES, TariffPlan
from core.models.identity_models import Company
from core.tracing.models import BillingSettlementSpan
from core.types import JsonObject

pytestmark = pytest.mark.xdist_group("billing_global_resource_base_prices_json")


def _settlement_span(
    *,
    span_id: str,
    trace_id: str,
    operation_name: str,
    company_id: str | None,
    user_id: str | None,
    service_name: str = "flows",
    attributes: JsonObject | None = None,
) -> BillingSettlementSpan:
    return BillingSettlementSpan(
        span_id=span_id,
        trace_id=trace_id,
        operation_name=operation_name,
        service_name=service_name,
        company_id=company_id,
        user_id=user_id,
        attributes=attributes if attributes is not None else {},
    )


@pytest.mark.asyncio
async def test_settle_span_rule_charge_idempotent(frontend_container, unique_id, system_user_id) -> None:
    company_id = f"bill_co_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Billing test co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=500.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    span_id = f"sp_{unique_id}"
    rule_id = f"rule_{unique_id}"
    span = _settlement_span(
        span_id=span_id,
        trace_id=f"tr_{unique_id}",
        operation_name=f"op.{unique_id}.run",
        company_id=company_id,
        user_id=system_user_id,
    )
    rule = SettlementRule(
        rule_id=rule_id,
        priority=1,
        resource_name="llm:*",
        usage_type="llm_request",
        quantity_from="const:1",
        match=SettlementRuleMatch(operation_name_prefix=f"op.{unique_id}."),
    )
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service

    uid1 = await billing.settle_span_rule_charge(
        span=span,
        rule=rule,
        settlement=settlement,
    )
    uid2 = await billing.settle_span_rule_charge(
        span=span,
        rule=rule,
        settlement=settlement,
    )
    assert uid1 == uid2

    raw = await frontend_container.shared_storage.get(
        f"billing:settled:{span_id}:{rule_id}",
        force_global=True,
    )
    assert raw is not None
    assert raw == uid1 or json.loads(raw) == uid1


@pytest.mark.asyncio
async def test_settle_pending_two_rules_two_usages(frontend_container, unique_id, system_user_id) -> None:
    company_id = f"bill_co2_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Billing test co2",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=500.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    span_id = f"sp2_{unique_id}"
    span = _settlement_span(
        span_id=span_id,
        trace_id=f"tr2_{unique_id}",
        operation_name=f"multi.{unique_id}.x",
        company_id=company_id,
        user_id=system_user_id,
    )
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.ALL_MATCHING,
        rules=[
            SettlementRule(
                rule_id=f"r1_{unique_id}",
                priority=1,
                resource_name="llm:*",
                usage_type="llm_request",
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix=f"multi.{unique_id}."),
            ),
            SettlementRule(
                rule_id=f"r2_{unique_id}",
                priority=2,
                resource_name="embedding:*",
                usage_type="embedding_request",
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix=f"multi.{unique_id}."),
            ),
        ],
    )
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service

    n = await billing.settle_pending_span_in_job(
        span=span,
        settlement=settlement,
        rules_doc=doc,
    )
    assert n == 2

    n2 = await billing.settle_pending_span_in_job(
        span=span,
        settlement=settlement,
        rules_doc=doc,
    )
    assert n2 == 0


@pytest.mark.asyncio
async def test_company_price_override_changes_unit_cost(frontend_container, unique_id, system_user_id) -> None:
    company_id = f"bill_co3_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Pricing co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=0.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    billing = frontend_container.billing_service
    global_only = await billing.get_effective_resource_base_prices()
    base_llm = float(global_only.get("llm", {}).get("*", 0.0))
    target = base_llm + 123.45

    await frontend_container.shared_storage.set(
        company_resource_prices_storage_key(company_id),
        json.dumps({"llm": {"*": target}}),
        force_global=True,
    )

    merged = await billing.get_effective_resource_base_prices_for_company(company_id)
    assert merged["llm"]["*"] == pytest.approx(target)
    mult = float(DEFAULT_TARIFF_PRICES[company.tariff_plan]["llm"]["*"])
    unit = await billing.get_resource_cost_for_company(company, "llm:any")
    assert unit == pytest.approx(target * mult)


@pytest.mark.asyncio
async def test_settle_span_rule_charge_missing_user_id_raises(
    frontend_container, unique_id: str, system_user_id: str
) -> None:
    company_id = f"bill_co7_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Co7",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=500.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    rule = SettlementRule(
        rule_id=f"fb_{unique_id}",
        priority=1,
        resource_name="llm:*",
        usage_type="llm_request",
        quantity_from="const:1",
        match=SettlementRuleMatch(operation_name_prefix=f"fb.{unique_id}."),
    )
    span = _settlement_span(
        span_id=f"sp7_{unique_id}",
        trace_id="t",
        operation_name=f"fb.{unique_id}.x",
        company_id=company_id,
        user_id=None,
    )
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service
    with pytest.raises(ValueError, match="user_id"):
        await billing.settle_span_rule_charge(
            span=span,
            rule=rule,
            settlement=settlement,
        )


@pytest.mark.asyncio
async def test_settle_pending_empty_rules_document_raises(
    frontend_container, unique_id: str, system_user_id: str
) -> None:
    company_id = f"bill_co8_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Co8",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=500.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    span = _settlement_span(
        span_id=f"sp8_{unique_id}",
        trace_id="t",
        operation_name="empty_rules",
        company_id=company_id,
        user_id=system_user_id,
    )
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service
    doc = SettlementRulesDocument()
    with pytest.raises(ValueError, match="at least one enabled rule"):
        await billing.settle_pending_span_in_job(
            span=span,
            settlement=settlement,
            rules_doc=doc,
        )


@pytest.mark.asyncio
async def test_settle_pending_rules_no_match_returns_zero(
    frontend_container, unique_id: str, system_user_id: str
) -> None:
    company_id = f"bill_co9_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Co9",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=500.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    span = _settlement_span(
        span_id=f"sp9_{unique_id}",
        trace_id="t",
        operation_name="nomatch.op",
        company_id=company_id,
        user_id=system_user_id,
    )
    doc = SettlementRulesDocument(
        rules=[
            SettlementRule(
                rule_id="only_other",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="other.prefix."),
            ),
        ],
    )
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service
    n = await billing.settle_pending_span_in_job(
        span=span,
        settlement=settlement,
        rules_doc=doc,
    )
    assert n == 0


@pytest.mark.asyncio
async def test_two_companies_same_resource_different_override_unit_cost(
    frontend_container, unique_id: str, system_user_id: str
) -> None:
    billing = frontend_container.billing_service
    mult = float(DEFAULT_TARIFF_PRICES[TariffPlan.FREE]["llm"]["*"])
    c_low = f"bill_low_{unique_id}"
    c_high = f"bill_high_{unique_id}"
    for cid in (c_low, c_high):
        co = Company(
            company_id=cid,
            name=cid,
            owner_user_id=system_user_id,
            members={system_user_id: ["owner"]},
            balance=0.0,
            monthly_budget=0.0,
            current_month_spent=0.0,
        )
        await frontend_container.company_repository.set(co)
    await frontend_container.shared_storage.set(
        company_resource_prices_storage_key(c_low),
        json.dumps({"llm": {"*": 1.0}}),
        force_global=True,
    )
    await frontend_container.shared_storage.set(
        company_resource_prices_storage_key(c_high),
        json.dumps({"llm": {"*": 10.0}}),
        force_global=True,
    )
    cl = await frontend_container.company_repository.get(c_low)
    ch = await frontend_container.company_repository.get(c_high)
    assert cl is not None and ch is not None
    low_u = await billing.get_resource_cost_for_company(cl, "llm:x")
    high_u = await billing.get_resource_cost_for_company(ch, "llm:x")
    assert low_u == pytest.approx(1.0 * mult)
    assert high_u == pytest.approx(10.0 * mult)
    await frontend_container.shared_storage.delete(
        company_resource_prices_storage_key(c_low), force_global=True
    )
    await frontend_container.shared_storage.delete(
        company_resource_prices_storage_key(c_high), force_global=True
    )

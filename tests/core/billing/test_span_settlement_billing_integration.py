"""
Интеграция: составной ключ settlement, правила, per-company прайс (реальные репозитории и storage).
"""

from __future__ import annotations

import json

import pytest

from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
)
from core.billing.span_billing_settlement import LEGACY_SPAN_ONLY_RULE_ID, SpanBillingSettlement
from core.billing.service import company_resource_prices_storage_key
from core.models.billing_models import DEFAULT_TARIFF_PRICES
from core.models.identity_models import Company


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
    span_dict = {
        "span_id": span_id,
        "trace_id": f"tr_{unique_id}",
        "operation_name": f"op.{unique_id}.run",
        "service_name": "flows",
        "company_id": company_id,
        "user_id": system_user_id,
        "attributes": {},
    }
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
        span_dict=span_dict,
        rule=rule,
        settlement=settlement,
        fallback_user_id="",
    )
    uid2 = await billing.settle_span_rule_charge(
        span_dict=span_dict,
        rule=rule,
        settlement=settlement,
        fallback_user_id="",
    )
    assert uid1 == uid2

    raw = await frontend_container.shared_storage.get(
        f"billing:settled:{span_id}:{rule_id}",
        force_global=True,
    )
    assert raw is not None
    assert json.loads(raw) == uid1


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
    span_dict = {
        "span_id": span_id,
        "trace_id": f"tr2_{unique_id}",
        "operation_name": f"multi.{unique_id}.x",
        "service_name": "flows",
        "company_id": company_id,
        "user_id": system_user_id,
        "attributes": {},
    }
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
                resource_name="tool:*",
                usage_type="tool_call",
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix=f"multi.{unique_id}."),
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
    assert n == 2

    n2 = await billing.settle_pending_span_in_job(
        span_dict=span_dict,
        settlement=settlement,
        fallback_user_id="",
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
async def test_legacy_settlement_uses_composite_and_old_key(frontend_container, unique_id, system_user_id) -> None:
    company_id = f"bill_co4_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Legacy co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=500.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)

    from core.tracing import attributes as trace_attr

    span_id = f"spL_{unique_id}"
    span_dict = {
        "span_id": span_id,
        "trace_id": f"trL_{unique_id}",
        "operation_name": "legacy.op",
        "service_name": "flows",
        "company_id": company_id,
        "user_id": system_user_id,
        "attributes": {
            trace_attr.ATTR_BILLING_RESOURCE_NAME: "llm:*",
            trace_attr.ATTR_BILLING_USAGE_TYPE: "llm_request",
            trace_attr.ATTR_BILLING_QUANTITY: 1,
        },
    }
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    billing = frontend_container.billing_service

    uid = await billing.settle_span_charge(
        span_dict=span_dict,
        settlement=settlement,
        fallback_user_id="",
    )
    assert uid

    same = await settlement.get_usage_id(span_id, LEGACY_SPAN_ONLY_RULE_ID)
    assert same == uid
    old = await frontend_container.shared_storage.get(f"billing:settled_span:{span_id}", force_global=True)
    assert old is not None

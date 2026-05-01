"""
Прайсы и расчёт unit cost / списаний в условиях, совпадающих с default_billing_resource_base_prices (conf.json).
Реальные репозитории, без моков BillingService.
"""

from __future__ import annotations

import copy
import json
import uuid

import pytest

from core.billing.service import BillingService, company_resource_prices_storage_key
from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRulesDocument,
)
from core.config.models import default_billing_resource_base_prices
from core.models.billing_models import DEFAULT_TARIFF_PRICES, TariffPlan, UsageType
from core.models.identity_models import Company

# Канон платформы (дублирует core.config.models.default_billing_resource_base_prices).
PRODUCTION_LIKE_BASE: dict[str, dict[str, float]] = {
    "llm": {"*": 0.0001},
    "embedding": {"*": 0.00005},
    "billing": {"rub": 1.0},
    "voice": {"session_minute": 0.01, "*": 0.0},
    "livekit": {
        "room_minute": 0.01,
        "egress_composite_minute": 0.05,
        "egress_segmented_minute": 0.02,
        "room_create": 0.01,
        "egress_composite": 0.05,
        "egress_segmented": 0.02,
        "*": 0.0,
    },
}


def _free_llm_mult() -> float:
    return float(DEFAULT_TARIFF_PRICES[TariffPlan.FREE]["llm"]["*"])


def _free_livekit_mult() -> float:
    return float(DEFAULT_TARIFF_PRICES[TariffPlan.FREE]["livekit"]["*"])


def _free_embedding_mult() -> float:
    return float(DEFAULT_TARIFF_PRICES[TariffPlan.FREE]["embedding"]["*"])


@pytest.mark.asyncio
async def test_static_catalog_matches_platform_default() -> None:
    assert default_billing_resource_base_prices() == PRODUCTION_LIKE_BASE


@pytest.mark.asyncio
async def test_production_like_llm_star_unit_cost(frontend_container, system_user_id) -> None:
    billing = frontend_container.billing_service
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    unit = await billing.get_resource_cost_for_company(company, "llm:gpt-4o")
    assert unit == pytest.approx(0.0001 * _free_llm_mult())


@pytest.mark.asyncio
async def test_tool_category_not_billed(frontend_container, system_user_id) -> None:
    billing = frontend_container.billing_service
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    assert await billing.get_resource_cost_for_company(company, "tool:any_id") == 0.0


@pytest.mark.asyncio
async def test_embedding_category_uses_embedding_tariff_bucket(
    frontend_container, unique_id, system_user_id
) -> None:
    """Как в проде: отдельная категория embedding + множитель из тарифа."""
    cid = f"emb_{unique_id}"
    prices = copy.deepcopy(PRODUCTION_LIKE_BASE)
    prices["embedding"] = {"*": 0.003, "text-embedding-3-small": 0.002}
    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        tariff_prices=DEFAULT_TARIFF_PRICES,
        resource_base_prices=prices,
        shared_storage=None,
    )
    company = Company(
        company_id=cid,
        name="Emb",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1000.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    m = _free_embedding_mult()
    assert await billing.get_resource_cost_for_company(fresh, "embedding:*") == pytest.approx(0.003 * m)
    assert await billing.get_resource_cost_for_company(fresh, "embedding:text-embedding-3-small") == pytest.approx(
        0.002 * m
    )


@pytest.mark.asyncio
async def test_resource_name_split_only_first_colon_for_category(
    frontend_container, unique_id, system_user_id
) -> None:
    """Категория до первого ':', остаток — ключ ресурса (в т.ч. с двоеточиями)."""
    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        tariff_prices=DEFAULT_TARIFF_PRICES,
        resource_base_prices=PRODUCTION_LIKE_BASE,
        shared_storage=None,
    )
    cid = f"split_{unique_id}"
    company = Company(
        company_id=cid,
        name="Split co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1000.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    unit = await billing.get_resource_cost_for_company(fresh, "llm:vendor:model:v2")
    assert unit == pytest.approx(0.0001 * _free_llm_mult())


@pytest.mark.asyncio
async def test_tariff_plan_basic_multiplier(frontend_container, unique_id, system_user_id) -> None:
    billing = frontend_container.billing_service
    cid = f"basic_{unique_id}"
    company = Company(
        company_id=cid,
        name="Basic co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1000.0,
        tariff_plan=TariffPlan.BASIC,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    m = float(DEFAULT_TARIFF_PRICES[TariffPlan.BASIC]["livekit"]["*"])
    assert await billing.get_resource_cost_for_company(fresh, "livekit:room_minute") == pytest.approx(0.01 * m)


@pytest.mark.asyncio
async def test_tariff_plan_premium_lowers_multiplier(frontend_container, unique_id, system_user_id) -> None:
    billing = frontend_container.billing_service
    cid = f"prem_{unique_id}"
    company = Company(
        company_id=cid,
        name="Premium co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1000.0,
        tariff_plan=TariffPlan.PREMIUM,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    mult = float(DEFAULT_TARIFF_PRICES[TariffPlan.PREMIUM]["llm"]["*"])
    unit = await billing.get_resource_cost_for_company(fresh, "llm:any")
    assert unit == pytest.approx(0.0001 * mult)


@pytest.mark.asyncio
async def test_global_storage_override_merges_llm_only(frontend_container, system_user_id) -> None:
    billing = frontend_container.billing_service
    key = "billing:resource_base_prices_json"
    prev = await frontend_container.shared_storage.get(key, force_global=True)
    try:
        await frontend_container.shared_storage.set(
            key,
            json.dumps({"llm": {"*": 0.01}}),
            force_global=True,
        )
        company = await frontend_container.company_repository.get("system")
        assert company is not None
        assert await billing.get_resource_cost_for_company(company, "llm:x") == pytest.approx(
            0.01 * _free_llm_mult()
        )
        assert await billing.get_resource_cost_for_company(company, "livekit:room_minute") == pytest.approx(
            0.01 * _free_livekit_mult()
        )
    finally:
        if prev is not None:
            await frontend_container.shared_storage.set(key, prev, force_global=True)
        else:
            await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_company_override_merges_over_global_and_static(
    frontend_container, unique_id, system_user_id
) -> None:
    billing = frontend_container.billing_service
    global_key = "billing:resource_base_prices_json"
    prev_g = await frontend_container.shared_storage.get(global_key, force_global=True)
    cid = f"merge_{unique_id}"
    ckey = company_resource_prices_storage_key(cid)
    company = Company(
        company_id=cid,
        name="Merge co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=10000.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    try:
        await frontend_container.shared_storage.set(
            global_key,
            json.dumps({"llm": {"*": 0.02}, "livekit": {"*": 0.07}}),
            force_global=True,
        )
        await frontend_container.shared_storage.set(
            ckey,
            json.dumps({"livekit": {"room_minute": 0.33}}),
            force_global=True,
        )
        assert await billing.get_resource_cost_for_company(fresh, "llm:x") == pytest.approx(0.02 * _free_llm_mult())
        assert await billing.get_resource_cost_for_company(fresh, "livekit:room_minute") == pytest.approx(
            0.33 * _free_livekit_mult()
        )
        assert await billing.get_resource_cost_for_company(fresh, "livekit:unknown_op") == pytest.approx(
            0.07 * _free_livekit_mult()
        )
    finally:
        await frontend_container.shared_storage.delete(ckey, force_global=True)
        if prev_g is not None:
            await frontend_container.shared_storage.set(global_key, prev_g, force_global=True)
        else:
            await frontend_container.shared_storage.delete(global_key, force_global=True)


@pytest.mark.asyncio
async def test_category_without_tariff_multiplier_is_one(
    frontend_container, unique_id, system_user_id
) -> None:
    """В тарифе нет категории — множитель 1.0."""
    cid = f"nocat_{unique_id}"
    prices = copy.deepcopy(PRODUCTION_LIKE_BASE)
    prices["custom_saas"] = {"*": 4.0, "api_call": 2.0}
    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        tariff_prices=DEFAULT_TARIFF_PRICES,
        resource_base_prices=prices,
        shared_storage=None,
    )
    company = Company(
        company_id=cid,
        name="Custom",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1000.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    assert await billing.get_resource_cost_for_company(fresh, "custom_saas:*") == pytest.approx(4.0)
    assert await billing.get_resource_cost_for_company(fresh, "custom_saas:api_call") == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_tariff_per_resource_multiplier_overrides_star(
    frontend_container, unique_id, system_user_id
) -> None:
    """Ветка category_multipliers[resource] (не только '*')."""
    cid = f"perres_{unique_id}"
    custom_tariff = copy.deepcopy(DEFAULT_TARIFF_PRICES)
    custom_tariff[TariffPlan.FREE] = {
        **copy.deepcopy(DEFAULT_TARIFF_PRICES[TariffPlan.FREE]),
        "llm": {"gpt-4o-prod": 2.5, "*": 1.5},
    }
    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        tariff_prices=custom_tariff,
        resource_base_prices=PRODUCTION_LIKE_BASE,
        shared_storage=None,
    )
    company = Company(
        company_id=cid,
        name="Per resource",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1000.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None
    assert await billing.get_resource_cost_for_company(fresh, "llm:gpt-4o-prod") == pytest.approx(0.0001 * 2.5)
    assert await billing.get_resource_cost_for_company(fresh, "llm:other") == pytest.approx(0.0001 * 1.5)


@pytest.mark.asyncio
async def test_settle_span_rule_charge_cost_matches_unit_times_quantity_livekit(
    frontend_container, unique_id, system_user_id
) -> None:
    from core.billing.settlement_rules import SettlementRule, SettlementRuleMatch
    from core.billing.span_billing_settlement import SpanBillingSettlement

    cid = f"cost_{unique_id}"
    company = Company(
        company_id=cid,
        name="Cost check",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=10000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None

    billing = frontend_container.billing_service
    unit = await billing.get_resource_cost_for_company(fresh, "livekit:room_minute")
    qty = 4
    expected = unit * qty

    rule = SettlementRule(
        rule_id=f"rule_cost_{unique_id}",
        resource_name="livekit:room_minute",
        usage_type="tool_call",
        quantity_from=f"const:{qty}",
        match=SettlementRuleMatch(operation_name_prefix=f"prod.{unique_id}."),
    )
    span_dict = {
        "span_id": f"sp_cost_{unique_id}",
        "trace_id": str(uuid.uuid4()),
        "operation_name": f"prod.{unique_id}.invoke",
        "service_name": "flows",
        "company_id": cid,
        "user_id": system_user_id,
        "attributes": {},
    }
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    usage_id = await billing.settle_span_rule_charge(
        span_dict=span_dict,
        rule=rule,
        settlement=settlement,
        fallback_user_id="",
    )
    recs = await frontend_container.usage_repository.admin_search_usage_records(company_id=cid, limit=30)
    row = next(r for r in recs if r.usage_id == usage_id)
    assert row.quantity == qty
    assert row.cost == pytest.approx(expected)
    assert row.resource_name == "livekit:room_minute"


@pytest.mark.asyncio
async def test_settle_span_rule_charge_llm_tokens_attr_production_base(
    frontend_container, unique_id, system_user_id
) -> None:
    from core.billing.settlement_rules import SettlementRule, SettlementRuleMatch
    from core.billing.span_billing_settlement import SpanBillingSettlement

    cid = f"tok_{unique_id}"
    company = Company(
        company_id=cid,
        name="Tok",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=100000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None

    billing = frontend_container.billing_service
    tokens = 10_000
    unit = await billing.get_resource_cost_for_company(fresh, "llm:*")
    expected = unit * tokens

    tok_attr = "platform.llm.total_tokens"
    rule = SettlementRule(
        rule_id=f"tok_rule_{unique_id}",
        resource_name="llm:*",
        usage_type="llm_request",
        quantity_from=f"attr:{tok_attr}",
        match=SettlementRuleMatch(operation_name_prefix=f"llmjob.{unique_id}."),
    )
    span_dict = {
        "span_id": f"sp_tok_{unique_id}",
        "trace_id": str(uuid.uuid4()),
        "operation_name": f"llmjob.{unique_id}.run",
        "service_name": "flows",
        "company_id": cid,
        "user_id": system_user_id,
        "attributes": {tok_attr: tokens},
    }
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    usage_id = await billing.settle_span_rule_charge(
        span_dict=span_dict,
        rule=rule,
        settlement=settlement,
        fallback_user_id="",
    )
    recs = await frontend_container.usage_repository.admin_search_usage_records(company_id=cid, limit=30)
    row = next(r for r in recs if r.usage_id == usage_id)
    assert row.quantity == tokens
    assert row.cost == pytest.approx(expected)
    assert row.usage_type == UsageType.LLM_REQUEST


@pytest.mark.asyncio
async def test_settle_pending_first_win_single_usage_high_priority_rule(
    frontend_container, unique_id, system_user_id
) -> None:
    """first_win + два матча: списание только по одному правилу; стоимость как у выбранного resource_name."""
    from core.billing.settlement_rules import SettlementRule, SettlementRuleMatch
    from core.billing.span_billing_settlement import SpanBillingSettlement

    cid = f"fw_{unique_id}"
    company = Company(
        company_id=cid,
        name="First win",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=10000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    fresh = await frontend_container.company_repository.get(cid)
    assert fresh is not None

    billing = frontend_container.billing_service
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.FIRST_WIN,
        rules=[
            SettlementRule(
                rule_id=f"r_lo_{unique_id}",
                priority=50,
                resource_name="livekit:*",
                usage_type="tool_call",
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix=f"fw.{unique_id}."),
            ),
            SettlementRule(
                rule_id=f"r_hi_{unique_id}",
                priority=5,
                resource_name="livekit:room_minute",
                usage_type="tool_call",
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix=f"fw.{unique_id}."),
            ),
        ],
    )
    span_dict = {
        "span_id": f"sp_fw_{unique_id}",
        "trace_id": str(uuid.uuid4()),
        "operation_name": f"fw.{unique_id}.x",
        "service_name": "flows",
        "company_id": cid,
        "user_id": system_user_id,
        "attributes": {},
    }
    settlement = SpanBillingSettlement(frontend_container.shared_storage)
    n = await billing.settle_pending_span_in_job(
        span_dict=span_dict,
        settlement=settlement,
        fallback_user_id="",
        rules_doc=doc,
    )
    assert n == 1
    unit_room = await billing.get_resource_cost_for_company(fresh, "livekit:room_minute")
    unit_star = await billing.get_resource_cost_for_company(fresh, "livekit:custom")
    assert unit_room != unit_star

    recs = await frontend_container.usage_repository.admin_search_usage_records(company_id=cid, limit=20)
    span_recs = [r for r in recs if r.metadata.get("span_id") == span_dict["span_id"]]
    assert len(span_recs) == 1
    assert span_recs[0].metadata.get("rule_id") == f"r_hi_{unique_id}"
    assert span_recs[0].resource_name == "livekit:room_minute"
    assert span_recs[0].cost == pytest.approx(unit_room)

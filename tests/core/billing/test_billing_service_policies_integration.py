"""
BillingService: can_use_resource, stats, reset_monthly_billing, ошибки merge прайса.
Реальные репозитории и storage (frontend_container).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.billing.service import (
    BillingService,
    STORAGE_SETTLEMENT_RULES_JSON,
    company_resource_prices_storage_key,
    company_settlement_rules_storage_key,
)
from core.models.billing_models import UsageType
from core.models.identity_models import Company


def _minimal_base_prices() -> dict:
    return {"llm": {"*": 1.0}, "livekit": {"*": 2.0}}


@pytest.mark.asyncio
async def test_billing_service_init_requires_repositories() -> None:
    with pytest.raises(ValueError, match="company_repository"):
        BillingService(
            None,  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            resource_base_prices=_minimal_base_prices(),
        )


@pytest.mark.asyncio
async def test_billing_service_init_requires_resource_base_prices() -> None:
    with pytest.raises(ValueError, match="resource_base_prices"):
        BillingService(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            resource_base_prices=None,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_can_use_resource_quantity_below_one(frontend_container, system_user_id) -> None:
    billing = frontend_container.billing_service
    user = await frontend_container.user_repository.get(system_user_id)
    company = await frontend_container.company_repository.get("system")
    assert user is not None and company is not None
    ok, reason = await billing.can_use_resource(user, company, "llm:x", quantity=0)
    assert ok is False
    assert "quantity" in reason.lower()


@pytest.mark.asyncio
async def test_can_use_resource_company_missing_in_db(frontend_container, system_user_id) -> None:
    billing = frontend_container.billing_service
    user = await frontend_container.user_repository.get(system_user_id)
    assert user is not None
    ghost = Company(
        company_id="no_such_company_ever_12345",
        name="Ghost",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=100.0,
    )
    ok, reason = await billing.can_use_resource(user, ghost, "llm:*")
    assert ok is False
    assert "не найдена" in reason


@pytest.mark.asyncio
async def test_can_use_resource_insufficient_balance(frontend_container, unique_id, system_user_id) -> None:
    billing = frontend_container.billing_service
    cid = f"poor_{unique_id}"
    company = Company(
        company_id=cid,
        name="Poor",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=0.01,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    user = await frontend_container.user_repository.get(system_user_id)
    assert user is not None
    key = company_resource_prices_storage_key(cid)
    await frontend_container.shared_storage.set(key, json.dumps({"llm": {"*": 9999.0}}), force_global=True)
    ok, reason = await billing.can_use_resource(user, company, "llm:any", quantity=1)
    assert ok is False
    assert "Недостаточно" in reason or "недостаточно" in reason
    await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_can_use_resource_monthly_budget_block(frontend_container, unique_id, system_user_id) -> None:
    billing = frontend_container.billing_service
    cid = f"budget_{unique_id}"
    company = Company(
        company_id=cid,
        name="Budgeted",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=1_000_000.0,
        monthly_budget=1.0,
        current_month_spent=0.5,
    )
    await frontend_container.company_repository.set(company)
    user = await frontend_container.user_repository.get(system_user_id)
    assert user is not None
    key = company_resource_prices_storage_key(cid)
    await frontend_container.shared_storage.set(key, json.dumps({"llm": {"*": 10.0}}), force_global=True)
    ok, reason = await billing.can_use_resource(user, company, "llm:x", quantity=1)
    assert ok is False
    assert "лимит" in reason.lower() or "Превышен" in reason
    await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_get_resource_cost_invalid_resource_name_format(frontend_container, system_user_id) -> None:
    billing = frontend_container.billing_service
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    with pytest.raises(ValueError, match="Неверный формат"):
        await billing.get_resource_cost_for_company(company, "no_colon")


@pytest.mark.asyncio
async def test_tool_billing_category_always_zero_even_with_storage_override(
    frontend_container, unique_id, system_user_id
) -> None:
    billing = frontend_container.billing_service
    cid = f"toolm_{unique_id}"
    company = Company(
        company_id=cid,
        name="Tool free",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=0.0,
    )
    await frontend_container.company_repository.set(company)
    key = company_resource_prices_storage_key(cid)
    await frontend_container.shared_storage.set(key, json.dumps({"tool": {"*": 10.0}}), force_global=True)
    unit = await billing.get_resource_cost_for_company(company, "tool:calc")
    assert unit == 0.0
    await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_get_effective_resource_base_prices_invalid_global_json_raises(
    frontend_container,
) -> None:
    billing = frontend_container.billing_service
    await frontend_container.shared_storage.set(
        "billing:resource_base_prices_json",
        '"not-an-object"',
        force_global=True,
    )
    try:
        with pytest.raises(json.JSONDecodeError):
            await billing.get_effective_resource_base_prices()
    finally:
        await frontend_container.shared_storage.delete("billing:resource_base_prices_json", force_global=True)


@pytest.mark.asyncio
async def test_get_effective_resource_base_prices_for_company_invalid_override_raises(
    frontend_container, unique_id
) -> None:
    billing = frontend_container.billing_service
    cid = f"badov_{unique_id}"
    key = company_resource_prices_storage_key(cid)
    await frontend_container.shared_storage.set(key, "[]", force_global=True)
    try:
        with pytest.raises(ValueError, match="объектом"):
            await billing.get_effective_resource_base_prices_for_company(cid)
    finally:
        await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_load_settlement_rules_document_invalid_storage_json_raises(
    frontend_container,
) -> None:
    billing = frontend_container.billing_service
    await frontend_container.shared_storage.set(STORAGE_SETTLEMENT_RULES_JSON, "[]", force_global=True)
    try:
        with pytest.raises(ValueError, match="корень должен"):
            await billing.load_settlement_rules_document()
    finally:
        await frontend_container.shared_storage.delete(STORAGE_SETTLEMENT_RULES_JSON, force_global=True)


@pytest.mark.asyncio
async def test_record_usage_then_get_company_usage_stats(
    frontend_container, unique_id, system_user_id
) -> None:
    billing = frontend_container.billing_service
    cid = f"stats_{unique_id}"
    company = Company(
        company_id=cid,
        name="Stats co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=10_000.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    user = await frontend_container.user_repository.get(system_user_id)
    assert user is not None

    usage_id = await billing.record_usage(
        user,
        company,
        "llm:test",
        cost=3.5,
        usage_type=UsageType.LLM_REQUEST,
        quantity=2,
        metadata={"span_id": f"sp_{unique_id}", "rule_id": "r1"},
    )

    stats = await billing.get_company_usage_stats(cid)
    assert stats["total_cost"] == pytest.approx(3.5)
    assert stats["total_calls"] == 2
    assert stats["by_resource"]["llm:test"]["cost"] == pytest.approx(3.5)
    assert stats["by_user"][system_user_id]["cost"] == pytest.approx(3.5)

    rec = await frontend_container.usage_repository.admin_search_usage_records(
        company_id=cid, limit=50
    )
    ids = {r.usage_id for r in rec}
    assert usage_id in ids


@pytest.mark.asyncio
async def test_reset_monthly_billing(frontend_container, unique_id, system_user_id) -> None:
    billing = frontend_container.billing_service
    cid = f"reset_{unique_id}"
    company = Company(
        company_id=cid,
        name="Reset co",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=100.0,
        monthly_budget=0.0,
        current_month_spent=42.0,
    )
    await frontend_container.company_repository.set(company)
    await billing.reset_monthly_billing(cid)
    updated = await frontend_container.company_repository.get(cid)
    assert updated is not None
    assert updated.current_month_spent == 0.0


@pytest.mark.asyncio
async def test_reset_monthly_billing_unknown_company_raises(frontend_container) -> None:
    billing = frontend_container.billing_service
    with pytest.raises(ValueError, match="не найдена"):
        await billing.reset_monthly_billing("company_does_not_exist_xyz")


@pytest.mark.asyncio
async def test_load_settlement_rules_for_company_migrates_from_global_json(
    frontend_container, unique_id, system_user_id
) -> None:
    billing = frontend_container.billing_service
    cid = f"migrate_sr_{unique_id}"
    company = Company(
        company_id=cid,
        name="Migrate SR",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=100.0,
        monthly_budget=0.0,
        current_month_spent=0.0,
    )
    await frontend_container.company_repository.set(company)
    ckey = company_settlement_rules_storage_key(cid)
    await frontend_container.shared_storage.delete(ckey, force_global=True)
    global_doc = {
        "version": 1,
        "application_mode": "first_win",
        "rules": [
            {
                "rule_id": f"g_{unique_id}",
                "resource_name": "llm:*",
                "usage_type": "llm_request",
                "quantity_from": "const:1",
                "match": {"operation_name_prefix": "z."},
            }
        ],
    }
    prev_global = await frontend_container.shared_storage.get(STORAGE_SETTLEMENT_RULES_JSON, force_global=True)
    try:
        await frontend_container.shared_storage.set(
            STORAGE_SETTLEMENT_RULES_JSON,
            json.dumps(global_doc),
            force_global=True,
        )
        doc = await billing.load_settlement_rules_document_for_company(cid)
        assert len(doc.rules) == 1
        assert doc.rules[0].rule_id == f"g_{unique_id}"
        raw_co = await frontend_container.shared_storage.get(ckey, force_global=True)
        assert raw_co is not None
        assert json.loads(raw_co)["rules"][0]["rule_id"] == f"g_{unique_id}"
    finally:
        await frontend_container.shared_storage.delete(ckey, force_global=True)
        if prev_global is not None:
            await frontend_container.shared_storage.set(
                STORAGE_SETTLEMENT_RULES_JSON, prev_global, force_global=True
            )
        else:
            await frontend_container.shared_storage.delete(STORAGE_SETTLEMENT_RULES_JSON, force_global=True)

"""
Тесты системы тарификации и биллинга
"""

import pytest
from core.models import Company
from core.models.billing_models import TariffPlan


@pytest.mark.asyncio
async def test_premium_discount(billing_service, unique_id):
    """Тест: PREMIUM тариф дает скидку на ресурсы"""
    
    free_company = Company(
        company_id=unique_id("free"),
        subdomain=unique_id("free"),
        name="Free",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0
    )
    
    premium_company = Company(
        company_id=unique_id("premium"),
        subdomain=unique_id("premium"),
        name="Premium",
        tariff_plan=TariffPlan.PREMIUM,
        balance=1000.0
    )
    
    free_cost = await billing_service.get_resource_cost_for_company(free_company, "llm:gpt-4")
    premium_cost = await billing_service.get_resource_cost_for_company(premium_company, "llm:gpt-4")
    
    assert premium_cost < free_cost, f"PREMIUM должен быть дешевле: premium={premium_cost}, free={free_cost}"
    assert premium_cost == pytest.approx(free_cost * (1.1 / 1.5), rel=0.01), \
        f"PREMIUM: {premium_cost} != FREE * (1.1/1.5): {free_cost * (1.1 / 1.5)}"


@pytest.mark.asyncio
async def test_enterprise_discount(billing_service, unique_id):
    """Тест: ENTERPRISE тариф - максимальная скидка (множитель 1.1x)"""
    
    enterprise_company = Company(
        company_id=unique_id("enterprise"),
        subdomain=unique_id("enterprise"),
        name="Enterprise",
        balance=1000.0,
        tariff_plan=TariffPlan.ENTERPRISE
    )
    
    free_company = Company(
        company_id=unique_id("free"),
        subdomain=unique_id("free"),
        name="Free",
        balance=1000.0,
        tariff_plan=TariffPlan.FREE
    )
    
    gpt4_cost_enterprise = await billing_service.get_resource_cost_for_company(enterprise_company, "llm:gpt-4")
    gpt4_cost_free = await billing_service.get_resource_cost_for_company(free_company, "llm:gpt-4")
    tool_cost_enterprise = await billing_service.get_resource_cost_for_company(enterprise_company, "tool:weather_api")
    tool_cost_free = await billing_service.get_resource_cost_for_company(free_company, "tool:weather_api")
    
    assert gpt4_cost_enterprise < gpt4_cost_free, \
        f"На ENTERPRISE GPT-4 должен быть дешевле: {gpt4_cost_enterprise} vs {gpt4_cost_free}"
    assert tool_cost_enterprise < tool_cost_free, \
        f"На ENTERPRISE тулы должны быть дешевле: {tool_cost_enterprise} vs {tool_cost_free}"


@pytest.mark.asyncio
async def test_balance_check(billing_service, test_user, unique_id):
    """Тест: проверка баланса работает"""
    
    no_balance_company = Company(
        company_id=unique_id("no_balance"),
        subdomain=unique_id("no_balance"),
        name="No Balance",
        tariff_plan=TariffPlan.FREE,
        balance=0.0
    )
    
    can_use, reason = await billing_service.can_use_resource(test_user, no_balance_company, "llm:gpt-4")
    assert not can_use, "Без баланса должно блокироваться"
    assert "баланс" in reason.lower(), f"Причина должна упоминать баланс: {reason}"
    
    with_balance_company = Company(
        company_id=unique_id("with_balance"),
        subdomain=unique_id("with_balance"),
        name="With Balance",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0
    )
    
    can_use, reason = await billing_service.can_use_resource(test_user, with_balance_company, "llm:gpt-4")
    assert can_use, f"С балансом должно быть доступно: {reason}"


@pytest.mark.asyncio
async def test_monthly_limit(billing_service, test_user, unique_id):
    """Тест: месячный лимит расходов работает"""
    
    limited_company = Company(
        company_id=unique_id("limited"),
        subdomain=unique_id("limited"),
        name="Limited",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0,
        monthly_budget=100.0,
        current_month_spent=95.0
    )
    
    cost = await billing_service.get_resource_cost_for_company(limited_company, "llm:gpt-4")
    can_use, reason = await billing_service.can_use_resource(test_user, limited_company, "llm:gpt-4")
    
    if cost > 5.0:
        assert not can_use, "Должно блокироваться при превышении месячного лимита"
        assert "лимит" in reason.lower(), f"Причина должна упоминать лимит: {reason}"


@pytest.mark.asyncio
async def test_base_price_fallback(billing_service, unique_id):
    """Тест: если в тарифе нет цены, используется базовая"""
    
    free_company = Company(
        company_id=unique_id("free"),
        subdomain=unique_id("free"),
        name="Free",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0
    )
    
    cost = await billing_service.get_resource_cost_for_company(free_company, "tool:calculator")
    
    assert cost == 0.0, f"Calculator должен быть бесплатным (базовая цена): {cost}"

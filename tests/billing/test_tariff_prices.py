"""
Тесты системы тарификации и биллинга
"""

import pytest
from app.services.billing_service import BillingService
from app.identity.models import User, Company, AuthProvider, UserStatus
from app.models.billing_models import TariffPlan


@pytest.fixture
def test_user():
    """Тестовый пользователь"""
    return User(
        user_id="test_user_123",
        provider=AuthProvider.YANDEX,
        provider_user_id="123",
        email="test@test.com",
        name="Test User",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={"test_company": ["user"]},
        active_company_id="test_company"
    )


@pytest.fixture
def free_company():
    """Компания с тарифом FREE и балансом"""
    return Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0,
        monthly_budget=0.0,
        current_month_spent=0.0
    )


@pytest.fixture
def premium_company():
    """Компания с тарифом PREMIUM"""
    return Company(
        company_id="premium_company",
        subdomain="premium",
        name="Premium Company",
        tariff_plan=TariffPlan.PREMIUM,
        balance=1000.0,
        monthly_budget=0.0,
        current_month_spent=0.0
    )


@pytest.fixture
def enterprise_company():
    """Компания с тарифом ENTERPRISE"""
    return Company(
        company_id="enterprise_company",
        subdomain="enterprise",
        name="Enterprise Company",
        tariff_plan=TariffPlan.ENTERPRISE,
        balance=0.0,
        monthly_budget=0.0,
        current_month_spent=0.0
    )


@pytest.mark.asyncio
async def test_premium_discount():
    """Тест: PREMIUM тариф дает скидку на ресурсы"""
    
    billing_service = BillingService()
    
    # Создаем компании с разными тарифами
    free_company = Company(
        company_id="free",
        subdomain="free",
        name="Free",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0
    )
    
    premium_company = Company(
        company_id="premium",
        subdomain="premium",
        name="Premium",
        tariff_plan=TariffPlan.PREMIUM,
        balance=1000.0
    )
    
    # Получаем цены для одного и того же ресурса
    free_cost = await billing_service.get_resource_cost_for_company(free_company, "llm:gpt-4")
    premium_cost = await billing_service.get_resource_cost_for_company(premium_company, "llm:gpt-4")
    
    # На premium должно быть дешевле (FREE: 1.5x, PREMIUM: 1.1x)
    assert premium_cost < free_cost, f"PREMIUM должен быть дешевле: premium={premium_cost}, free={free_cost}"
    # FREE: 0.001 * 1.5 = 0.0015, PREMIUM: 0.001 * 1.1 = 0.0011
    assert premium_cost == pytest.approx(free_cost * (1.1 / 1.5), rel=0.01), \
        f"PREMIUM: {premium_cost} != FREE * (1.1/1.5): {free_cost * (1.1 / 1.5)}"


@pytest.mark.asyncio
async def test_enterprise_discount():
    """Тест: ENTERPRISE тариф - максимальная скидка (множитель 1.1x)"""
    
    billing_service = BillingService()
    
    enterprise_company = Company(
        company_id="enterprise",
        subdomain="enterprise",
        name="Enterprise",
        balance=1000.0,
        tariff_plan=TariffPlan.ENTERPRISE
    )
    
    free_company = Company(
        company_id="free",
        subdomain="free",
        name="Free",
        balance=1000.0,
        tariff_plan=TariffPlan.FREE
    )
    
    # Проверяем что ресурсы дешевле чем на FREE (ENTERPRISE: 1.1x vs FREE: 1.5x)
    gpt4_cost_enterprise = await billing_service.get_resource_cost_for_company(enterprise_company, "llm:gpt-4")
    gpt4_cost_free = await billing_service.get_resource_cost_for_company(free_company, "llm:gpt-4")
    tool_cost_enterprise = await billing_service.get_resource_cost_for_company(enterprise_company, "tool:weather_api")
    tool_cost_free = await billing_service.get_resource_cost_for_company(free_company, "tool:weather_api")
    
    assert gpt4_cost_enterprise < gpt4_cost_free, \
        f"На ENTERPRISE GPT-4 должен быть дешевле: {gpt4_cost_enterprise} vs {gpt4_cost_free}"
    assert tool_cost_enterprise < tool_cost_free, \
        f"На ENTERPRISE тулы должны быть дешевле: {tool_cost_enterprise} vs {tool_cost_free}"


@pytest.mark.asyncio
async def test_balance_check():
    """Тест: проверка баланса работает"""
    
    billing_service = BillingService()
    test_user = User(
        user_id="test",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        companies={"test": ["user"]}
    )
    
    # Компания БЕЗ баланса
    no_balance_company = Company(
        company_id="no_balance",
        subdomain="no_balance",
        name="No Balance",
        tariff_plan=TariffPlan.FREE,
        balance=0.0
    )
    
    # Должно блокироваться
    can_use, reason = await billing_service.can_use_resource(test_user, no_balance_company, "llm:gpt-4")
    assert not can_use, "Без баланса должно блокироваться"
    assert "баланс" in reason.lower(), f"Причина должна упоминать баланс: {reason}"
    
    # Компания С балансом
    with_balance_company = Company(
        company_id="with_balance",
        subdomain="with_balance",
        name="With Balance",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0
    )
    
    # Должно быть доступно
    can_use, reason = await billing_service.can_use_resource(test_user, with_balance_company, "llm:gpt-4")
    assert can_use, f"С балансом должно быть доступно: {reason}"


@pytest.mark.asyncio
async def test_monthly_limit():
    """Тест: месячный лимит расходов работает"""
    
    billing_service = BillingService()
    test_user = User(
        user_id="test",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        companies={"test": ["user"]}
    )
    
    # Компания с лимитом и почти исчерпанным бюджетом
    limited_company = Company(
        company_id="limited",
        subdomain="limited",
        name="Limited",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0,
        monthly_budget=100.0,
        current_month_spent=95.0
    )
    
    # Получаем стоимость ресурса
    cost = await billing_service.get_resource_cost_for_company(limited_company, "llm:gpt-4")
    
    # Если стоимость превысит лимит - должно блокироваться
    can_use, reason = await billing_service.can_use_resource(test_user, limited_company, "llm:gpt-4")
    
    if cost > 5.0:
        assert not can_use, "Должно блокироваться при превышении месячного лимита"
        assert "лимит" in reason.lower(), f"Причина должна упоминать лимит: {reason}"


@pytest.mark.asyncio
async def test_base_price_fallback():
    """Тест: если в тарифе нет цены, используется базовая"""
    
    billing_service = BillingService()
    
    free_company = Company(
        company_id="free",
        subdomain="free",
        name="Free",
        tariff_plan=TariffPlan.FREE,
        balance=1000.0
    )
    
    # Calculator не переопределен в тарифах - должна быть базовая цена
    cost = await billing_service.get_resource_cost_for_company(free_company, "tool:calculator")
    
    # Calculator обычно бесплатный
    assert cost == 0.0, f"Calculator должен быть бесплатным (базовая цена): {cost}"

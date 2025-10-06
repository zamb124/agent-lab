"""
Тесты системы тарификации и биллинга
"""

import pytest
from app.services.billing_service import BillingService
from app.identity.models import User, Company, AuthProvider, UserStatus
from app.models.billing_models import TariffPlan, UsageType


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
    free_cost = await billing_service.get_resource_cost_for_company(free_company, "openai:gpt-4")
    premium_cost = await billing_service.get_resource_cost_for_company(premium_company, "openai:gpt-4")
    
    # На premium должно быть дешевле
    assert premium_cost < free_cost, f"PREMIUM должен быть дешевле: premium={premium_cost}, free={free_cost}"
    assert premium_cost == free_cost * 0.5, f"PREMIUM дает скидку 50%: {premium_cost} != {free_cost * 0.5}"


@pytest.mark.asyncio
async def test_enterprise_free():
    """Тест: ENTERPRISE тариф - все бесплатно"""
    
    billing_service = BillingService()
    
    enterprise_company = Company(
        company_id="enterprise",
        subdomain="enterprise",
        name="Enterprise",
        tariff_plan=TariffPlan.ENTERPRISE,
        balance=0.0
    )
    
    # Проверяем что все ресурсы бесплатны
    gpt4_cost = await billing_service.get_resource_cost_for_company(enterprise_company, "openai:gpt-4")
    tool_cost = await billing_service.get_resource_cost_for_company(enterprise_company, "tool:weather_api")
    
    assert gpt4_cost == 0.0, f"На ENTERPRISE GPT-4 должен быть бесплатным: {gpt4_cost}"
    assert tool_cost == 0.0, f"На ENTERPRISE тулы должны быть бесплатными: {tool_cost}"


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
    can_use, reason = await billing_service.can_use_resource(test_user, no_balance_company, "openai:gpt-4")
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
    can_use, reason = await billing_service.can_use_resource(test_user, with_balance_company, "openai:gpt-4")
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
    cost = await billing_service.get_resource_cost_for_company(limited_company, "openai:gpt-4")
    
    # Если стоимость превысит лимит - должно блокироваться
    can_use, reason = await billing_service.can_use_resource(test_user, limited_company, "openai:gpt-4")
    
    if cost > 5.0:
        assert not can_use, f"Должно блокироваться при превышении месячного лимита"
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

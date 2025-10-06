"""
Простой тест системы биллинга.
"""

import pytest
from pathlib import Path
import sys

# Добавляем backend в путь
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))


def test_billing_models_import():
    """Тест что модели биллинга импортируются без ошибок"""
    from app.models.billing_models import UsageRecord, TariffPlan, TARIFF_PRICES
    from app.services.billing_service import BillingService
    from app.core.tool_decorator import tool
    from app.core.llm_billing_wrapper import ChatOpenAIWithBilling
    
    assert TariffPlan.FREE == "free"
    assert TariffPlan.BASIC == "basic"
    assert TariffPlan.PREMIUM == "premium"
    assert TariffPlan.ENTERPRISE == "enterprise"
    
    # Проверяем что тарифные цены настроены
    assert "openai" in TARIFF_PRICES[TariffPlan.FREE]
    assert "openai" in TARIFF_PRICES[TariffPlan.PREMIUM]
    assert TARIFF_PRICES[TariffPlan.PREMIUM]["openai"]["*"] == 0.5  # Скидка 50%
    
    print("✅ Все модели биллинга импортируются корректно")


def test_tool_decorator():
    """Тест платформенного декоратора @tool"""
    from app.core.tool_decorator import tool
    
    @tool(cost=0.5, billing_name="test_tool")
    def test_function(text: str) -> str:
        """Тестовая функция"""
        return f"Result: {text}"
    
    # Проверяем что метаданные сохранились
    assert hasattr(test_function, '_platform_cost')
    assert test_function._platform_cost == 0.5
    assert test_function._platform_billing_name == "test_tool"
    assert test_function._is_platform_tool == True
    
    # Проверяем что функция работает
    result = test_function.invoke({"text": "hello"})
    assert "Result: hello" in result
    
    print("✅ Декоратор @tool работает корректно")


def test_company_model_with_billing():
    """Тест что модель Company содержит поля биллинга"""
    from app.identity.models import Company
    
    company = Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        tariff_plan="basic",
        monthly_budget=1000.0,
        current_month_spent=50.0
    )
    
    assert company.tariff_plan == "basic"
    assert company.monthly_budget == 1000.0
    assert company.current_month_spent == 50.0
    
    print("✅ Модель Company с биллинг полями работает")


def test_toolreference_with_billing():
    """Тест что ToolReference содержит поля биллинга"""
    from app.models.core_models import ToolReference, CodeMode
    
    tool_ref = ToolReference(
        tool_id="test_tool",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="app.tools.test",
        cost=0.3,
        billing_name="custom_name",
        free_for_plans=["premium"],
        tariff_limits={"free": 0, "basic": 10}
    )
    
    assert tool_ref.cost == 0.3
    assert tool_ref.billing_name == "custom_name"
    assert "premium" in tool_ref.free_for_plans
    assert tool_ref.tariff_limits["basic"] == 10
    
    print("✅ ToolReference с биллинг полями работает")


if __name__ == "__main__":
    test_billing_models_import()
    test_tool_decorator()
    test_company_model_with_billing()
    test_toolreference_with_billing()
    print("🎉 Все простые тесты биллинга прошли!")

"""
Простой тест системы биллинга.
"""


def test_billing_models_import():
    """Тест что модели биллинга импортируются без ошибок"""
    from core.models.billing_models import TariffPlan, DEFAULT_TARIFF_PRICES as TARIFF_PRICES
    
    assert TariffPlan.FREE == "free"
    assert TariffPlan.BASIC == "basic"
    assert TariffPlan.PREMIUM == "premium"
    assert TariffPlan.ENTERPRISE == "enterprise"
    
    # Проверяем что тарифные цены настроены
    assert "llm" in TARIFF_PRICES[TariffPlan.FREE]
    assert "tools" in TARIFF_PRICES[TariffPlan.FREE]
    assert TARIFF_PRICES[TariffPlan.FREE]["llm"]["*"] == 1.5  # Самый дорогой
    assert TARIFF_PRICES[TariffPlan.BASIC]["llm"]["*"] == 1.25
    assert TARIFF_PRICES[TariffPlan.PREMIUM]["llm"]["*"] == 1.1
    assert TARIFF_PRICES[TariffPlan.ENTERPRISE]["llm"]["*"] == 1.1


def test_tool_decorator():
    """Тест платформенного декоратора @tool"""
    from apps.agents.services.tool_decorator import tool, ToolReturn
    
    # Тест обычного tool
    @tool(cost=0.5, billing_name="test_tool")
    def test_function(text: str) -> str:
        """Тестовая функция"""
        return f"Result: {text}"
    
    # Проверяем что метаданные сохранились
    assert hasattr(test_function, '_platform_cost')
    assert test_function._platform_cost == 0.5
    assert test_function._platform_billing_name == "test_tool"
    assert test_function._is_platform_tool
    
    # Проверяем что функция работает в обычном Python коде
    result = test_function.invoke({"text": "hello"})
    assert "Result: hello" in result
    
    # Тест универсального tool с ToolReturn
    @tool(cost=0.1, billing_name="universal_tool", title="Универсальный тул")
    def universal_function(key: str, value: str) -> ToolReturn:
        """Универсальная функция"""
        return ToolReturn(
            delta={"store": {key: value}},  # Для LangGraph
            result=f"Сохранено: {key} = {value}"  # Для Python кода
        )
    
    # Проверяем метаданные
    assert universal_function._platform_cost == 0.1
    assert universal_function._platform_title == "Универсальный тул"
    
    # Проверяем что в Python коде возвращается только result
    result = universal_function.invoke({"key": "test", "value": "data"})
    assert "Сохранено: test = data" in result


def test_company_model_with_billing():
    """Тест что модель Company содержит поля биллинга"""
    from core.models import Company
    from core.models.billing_models import TariffPlan
    
    company = Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        tariff_plan=TariffPlan.BASIC,
        monthly_budget=1000.0,
        current_month_spent=50.0
    )
    
    assert company.tariff_plan == "basic"
    assert company.monthly_budget == 1000.0
    assert company.current_month_spent == 50.0


def test_toolreference_with_billing():
    """Тест что ToolReference содержит поля биллинга"""
    from apps.agents.models.core_models import ToolReference, CodeMode
    
    tool_ref = ToolReference(
        tool_id="test_tool",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="apps.agents.tools.test",
        cost=0.3,
        billing_name="custom_name",
        free_for_plans=["premium"],
        tariff_limits={"free": 0, "basic": 10}
    )
    
    assert tool_ref.cost == 0.3
    assert tool_ref.billing_name == "custom_name"
    assert "premium" in tool_ref.free_for_plans
    assert tool_ref.tariff_limits["basic"] == 10

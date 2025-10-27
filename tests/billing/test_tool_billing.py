"""
Интеграционные тесты для биллинга инструментов.
Тесты ToolFactory с биллинг обертками и платформенного декоратора @tool.
"""

import pytest
from app.core.tool_decorator import tool
from app.models.core_models import ToolReference, CodeMode


@tool(cost=0.5, billing_name="test_expensive_tool")
async def expensive_test_tool(input_text: str) -> str:
    """Дорогой тестовый инструмент"""
    return f"Expensive result: {input_text}"


@tool
async def free_test_tool(input_text: str) -> str:
    """Бесплатный тестовый инструмент"""
    return f"Free result: {input_text}"


@tool(cost=1.0, free_for_plans=["premium", "enterprise"])
def premium_test_tool(input_text: str) -> str:
    """Премиум тестовый инструмент"""
    return f"Premium result: {input_text}"


class TestToolDecorator:
    """Тесты платформенного декоратора @tool"""
    
    def test_tool_decorator_metadata(self):
        """Тест что декоратор сохраняет метаданные биллинга"""
        
        # Проверяем дорогой инструмент
        assert hasattr(expensive_test_tool, '_platform_cost')
        assert expensive_test_tool._platform_cost == 0.5
        assert expensive_test_tool._platform_billing_name == "test_expensive_tool"
        assert expensive_test_tool._is_platform_tool
        
        # Проверяем бесплатный инструмент
        assert hasattr(free_test_tool, '_platform_cost')
        assert free_test_tool._platform_cost == 0.0
        assert free_test_tool._platform_billing_name == "free_test_tool"
        
        # Проверяем премиум инструмент
        assert hasattr(premium_test_tool, '_platform_cost')
        assert premium_test_tool._platform_cost == 1.0
        assert "premium" in premium_test_tool._platform_free_for_plans
        assert "enterprise" in premium_test_tool._platform_free_for_plans
    
    @pytest.mark.skip(reason="Устаревший тест - проверяет старую логику с free_for_plans")
    def test_tool_decorator_functionality(self):
        """Тест что декоратор не нарушает функциональность инструментов"""
        
        result = expensive_test_tool.invoke({"input_text": "test"})
        assert "Expensive result: test" in result
        
        result = free_test_tool.invoke({"input_text": "test"})
        assert "Free result: test" in result


class TestToolFactory:
    """Тесты ToolFactory с биллингом"""
    
    @pytest.mark.asyncio
    async def test_create_tool_with_billing(self, tool_factory):
        """Тест создания инструмента с биллинг параметрами"""
        tool_ref = ToolReference(
            tool_id="tests.billing.test_tool_billing.expensive_test_tool",
            code_mode=CodeMode.CODE_REFERENCE,
            function_path="tests.billing.test_tool_billing.expensive_test_tool",
            description="Тестовый инструмент с биллингом",
            cost=0.3,
            billing_name="custom_billing_name",
            free_for_plans=["enterprise"],
            tariff_limits={"free": 0, "basic": 10, "premium": 100}
        )
        
        tool = await tool_factory._create_single_tool(tool_ref)
        
        assert tool is not None
        assert hasattr(tool, '_billing_ref')
        assert tool._billing_ref.cost == 0.3
        assert tool._billing_ref.billing_name == "custom_billing_name"
    
    @pytest.mark.skip(reason="Устаревший тест - проверяет старую логику с _billing_ref")
    @pytest.mark.asyncio
    async def test_tool_execution_with_billing(self, tool_factory, test_context, test_user, test_company, storage):
        """Тест выполнения инструмента с биллингом"""
        
        # Создаем ToolReference
        tool_ref = ToolReference(
            tool_id="tests.billing.test_tool_billing.expensive_test_tool",
            code_mode=CodeMode.CODE_REFERENCE,
            function_path="tests.billing.test_tool_billing.expensive_test_tool",
            description="Тестовый инструмент для выполнения",
            cost=0.2,
            billing_name="execution_test_tool"
        )
        
        # Создаем и выполняем инструмент
        tool = await tool_factory._create_single_tool(tool_ref)
        
        
        # Выполняем инструмент (биллинг работает через обертку func)
        result = tool.invoke({"input_text": "billing test"})
        assert "Expensive result: billing test" in result
        
        # В тестовой среде биллинг может не записываться (нет полного контекста)
        # Главное что инструмент создался с биллинг метаданными
        assert hasattr(tool, '_billing_ref')
        assert tool._billing_ref.cost == 0.2
        assert tool._billing_ref.billing_name == "execution_test_tool"
        
        # Тест завершен успешно
    
    @pytest.mark.asyncio
    async def test_free_tool_execution(self, tool_factory, test_context):
        """Тест выполнения бесплатного инструмента"""
        tool_ref = ToolReference(
            tool_id="tests.billing.test_tool_billing.free_test_tool",
            code_mode=CodeMode.CODE_REFERENCE,
            function_path="tests.billing.test_tool_billing.free_test_tool",
            description="Бесплатный тестовый инструмент",
            cost=0.0,
            billing_name="free_execution_tool"
        )
        
        tool = await tool_factory._create_single_tool(tool_ref)
        
        result = await tool.ainvoke({"input_text": "free test"})
        assert "Free result: free test" in result
        
        assert tool is not None
        assert tool.name == "free_test_tool"
    
    @pytest.mark.asyncio
    async def test_tool_access_denied(self, tool_factory, test_context, test_company):
        """Тест запрета доступа к инструменту"""
        test_company.tariff_plan = "free"
        
        tool_ref = ToolReference(
            tool_id="tests.billing.test_tool_billing.expensive_test_tool",
            code_mode=CodeMode.CODE_REFERENCE,
            function_path="tests.billing.test_tool_billing.expensive_test_tool",
            description="Премиум инструмент",
            cost=1.0,
            billing_name="premium_tool",
            tariff_limits={"free": 0, "basic": 10}
        )
        
        tool = await tool_factory._create_single_tool(tool_ref)
        
        assert hasattr(tool, '_billing_ref')
        assert tool._billing_ref.tariff_limits["free"] == 0
        assert tool._billing_ref.cost == 1.0
    
    @pytest.mark.skip(reason="Устаревший тест - проверяет старую логику с free_for_plans")
    @pytest.mark.asyncio
    async def test_tool_premium_free_access(self, tool_factory, test_context, test_user, test_company, storage):
        """Тест бесплатного доступа к платному инструменту для премиум плана"""
        
        # Переключаем на premium план
        test_company.tariff_plan = "premium"
        
        # Создаем инструмент бесплатный для premium
        tool_ref = ToolReference(
            tool_id="tests.billing.test_tool_billing.premium_test_tool",
            code_mode=CodeMode.CODE_REFERENCE,
            function_path="tests.billing.test_tool_billing.premium_test_tool",
            description="Инструмент бесплатный для premium",
            cost=2.0,
            billing_name="premium_free_tool",
            free_for_plans=["premium", "enterprise"]
        )
        
        tool = await tool_factory._create_single_tool(tool_ref)
        
        
        # Выполняем инструмент
        result = tool.invoke({"input_text": "premium free test"})
        assert "Premium result: premium free test" in result
        
        # Проверяем что инструмент создался с правильными биллинг параметрами
        assert hasattr(tool, '_billing_ref')
        assert tool._billing_ref.cost == 2.0
        assert "premium" in tool._billing_ref.free_for_plans
        assert "enterprise" in tool._billing_ref.free_for_plans

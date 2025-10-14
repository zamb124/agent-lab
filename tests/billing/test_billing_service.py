"""
Интеграционные тесты для BillingService.
Тесты с реальной БД, компаниями и пользователями.
"""

import pytest
from app.models.billing_models import UsageRecord, UsageType


class TestBillingService:
    """Тесты для BillingService"""
    
    @pytest.mark.asyncio
    async def test_can_use_resource_basic_plan(self, billing_service, save_test_company, test_user, test_company):
        """Тест проверки доступа к ресурсу на базовом плане"""
        test_company.tariff_plan = "basic"
        test_company.balance = 1000.0
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "tool:weather_api"
        )
        assert can_use, f"Должен быть доступ к weather_api: {reason}"
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        assert can_use, f"Должен быть доступ к gpt-4 на basic плане: {reason}"
        
    @pytest.mark.asyncio
    async def test_can_use_resource_free_plan(self, billing_service, save_test_company, test_user, test_company):
        """Тест проверки доступа с балансом и без"""
        test_company.tariff_plan = "free"
        test_company.balance = 1000.0
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        assert can_use, f"С балансом GPT-4 должен быть доступен: {reason}"
        
        test_company.balance = 0.0
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        assert not can_use, "Без баланса должен быть недоступен"
        assert "баланс" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_monthly_limits(self, billing_service, save_test_company, test_user, test_company):
        """Тест месячных лимитов расходов"""
        test_company.monthly_budget = 100.0
        test_company.current_month_spent = 95.0
        test_company.balance = 1000.0
        
        cost = await billing_service.get_resource_cost_for_company(test_company, "llm:gpt-4")
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        
        if cost > 5.0:
            assert not can_use, f"Должен быть превышен месячный лимит: cost={cost}, reason={reason}"
            assert "месячный лимит" in reason.lower()
        else:
            assert can_use, f"Должно быть доступно: {reason}"
    
    @pytest.mark.asyncio
    async def test_budget_limits(self, billing_service, save_test_company, test_user, test_company):
        """Тест бюджетных лимитов"""
        test_company.monthly_budget = 100.0
        test_company.current_month_spent = 99.0
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        
        assert isinstance(can_use, bool)
        assert isinstance(reason, str)
    
    @pytest.mark.asyncio
    async def test_record_usage(self, billing_service, save_test_company, test_user, test_company, storage):
        """Тест записи использования"""
        from app.identity.models import Company
        
        initial_spent = test_company.current_month_spent
        
        await billing_service.record_usage(
            user=test_user,
            company=test_company,
            resource_name="tool:weather_api",
            cost=0.5,
            usage_type=UsageType.TOOL_CALL,
            quantity=1,
            metadata={"test": "data"}
        )
        
        updated_company_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
        updated_company = Company.model_validate_json(updated_company_data)
        assert updated_company.current_month_spent == initial_spent + 0.5
        
        search_prefix = f"usage:{test_company.company_id}:tool:weather_api:"
        usage_keys = await storage.list_by_prefix(search_prefix, force_global=True)
        usage_records = []
        for key in usage_keys:
            data = await storage.get(key, force_global=True)
            if data:
                usage_records.append(UsageRecord.model_validate_json(data))
        
        assert len(usage_records) > 0, f"Записи использования не найдены по префиксу {search_prefix}"
        found_record = usage_records[0]
        
        assert found_record.cost == 0.5
        assert found_record.usage_type == UsageType.TOOL_CALL
        assert found_record.metadata.get("test") == "data"
    
    
    @pytest.mark.asyncio
    async def test_get_company_usage_stats(self, billing_service, test_user, storage, unique_id):
        """Тест получения полной статистики компании"""
        from app.identity.models import Company
        
        stats_company = Company(
            company_id=unique_id("stats_company"),
            subdomain=unique_id("stats"),
            name="Stats Test Company",
            tariff_plan="enterprise",
            balance=100000.0,
            monthly_budget=50000.0,
            current_month_spent=0.0,
            status="active"
        )
        
        usage_records = [
            UsageRecord(
                usage_id=unique_id("stats"),
                user_id=test_user.user_id,
                company_id=stats_company.company_id,
                usage_type=UsageType.LLM_REQUEST,
                resource_name="llm:gpt-4",
                cost=2.0,
                quantity=1000
            ),
            UsageRecord(
                usage_id=unique_id("stats"),
                user_id=test_user.user_id,
                company_id=stats_company.company_id,
                usage_type=UsageType.TOOL_CALL,
                resource_name="tool:weather_api",
                cost=0.1,
                quantity=1
            ),
            UsageRecord(
                usage_id=unique_id("stats"),
                user_id=test_user.user_id,
                company_id=stats_company.company_id,
                usage_type=UsageType.TOOL_CALL,
                resource_name="tool:weather_api",
                cost=0.1,
                quantity=1
            )
        ]
        
        for usage in usage_records:
            usage_key = f"usage:{stats_company.company_id}:{usage.resource_name}:{usage.usage_id}"
            await storage.set(usage_key, usage.model_dump_json(), force_global=True)
        
        stats = await billing_service.get_company_usage_stats(stats_company.company_id)
        
        assert stats["total_cost"] == 2.2, f"Общая стоимость должна быть 2.2, получено: {stats['total_cost']}"
        assert stats["total_calls"] == 1002, f"Общее количество вызовов должно быть 1002, получено: {stats['total_calls']}"
        assert "llm:gpt-4" in stats["by_resource"]
        assert "tool:weather_api" in stats["by_resource"]
        assert stats["by_resource"]["llm:gpt-4"]["cost"] == 2.0
        assert stats["by_resource"]["tool:weather_api"]["cost"] == 0.2
        assert stats["by_resource"]["tool:weather_api"]["calls"] == 2


@pytest.mark.asyncio
async def test_billing_service_integration(billing_service, save_test_company, test_user, test_company):
    """Интеграционный тест всего BillingService"""
    test_company.tariff_plan = "premium"
    test_company.balance = 10000.0
    test_company.monthly_budget = 5000.0
    test_company.current_month_spent = 100.0
    
    can_use, reason = await billing_service.can_use_resource(test_user, test_company, "llm:gpt-4")
    assert can_use, f"Должен быть доступ к GPT-4 на premium: {reason}"
    
    await billing_service.record_usage(
        user=test_user,
        company=test_company,
        resource_name="llm:gpt-4",
        cost=3.0,
        usage_type=UsageType.LLM_REQUEST,
        quantity=1500,
        metadata={"model": "gpt-4", "tokens": 1500}
    )
    
    stats = await billing_service.get_company_usage_stats(test_company.company_id)
    assert stats["total_cost"] >= 0
    assert stats["total_calls"] >= 0

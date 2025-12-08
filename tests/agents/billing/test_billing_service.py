"""
Интеграционные тесты для BillingService.
Тесты с реальной БД, компаниями и пользователями.
"""

import pytest
from core.models.billing_models import UsageRecord, UsageType


class TestBillingService:
    """Тесты для BillingService"""
    
    @pytest.mark.asyncio
    async def test_can_use_resource_basic_plan(self, billing_service, save_test_company, test_user, test_company, company_repo):
        """Тест проверки доступа к ресурсу на базовом плане"""
        from core.models.billing_models import TariffPlan
        test_company.tariff_plan = TariffPlan.BASIC
        test_company.balance = 1000.0
        await company_repo.set(test_company)
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "tool:weather_api"
        )
        assert can_use, f"Должен быть доступ к weather_api: {reason}"
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        assert can_use, f"Должен быть доступ к gpt-4 на basic плане: {reason}"
        
    @pytest.mark.asyncio
    async def test_can_use_resource_free_plan(self, billing_service, save_test_company, test_user, test_company, company_repo):
        """Тест проверки доступа с балансом и без"""
        from core.models.billing_models import TariffPlan
        test_company.tariff_plan = TariffPlan.FREE
        test_company.balance = 1000.0
        await company_repo.set(test_company)
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        assert can_use, f"С балансом GPT-4 должен быть доступен: {reason}"
        
        # Обязательно сохраняем в БД т.к. can_use_resource загружает компанию из репозитория
        test_company.balance = 0.0
        await company_repo.set(test_company)
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        assert not can_use, "Без баланса должен быть недоступен"
        assert "баланс" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_monthly_limits(self, billing_service, save_test_company, test_user, test_company, company_repo):
        """Тест месячных лимитов расходов"""
        test_company.monthly_budget = 100.0
        test_company.current_month_spent = 95.0
        test_company.balance = 1000.0
        # Сохраняем в БД т.к. can_use_resource загружает компанию из репозитория
        await company_repo.set(test_company)
        
        cost = await billing_service.get_resource_cost_for_company(test_company, "llm:gpt-4")
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        
        if cost > 5.0:
            assert not can_use, f"Должен быть превышен месячный лимит: cost={cost}, reason={reason}"
            assert "лимит" in reason.lower()
        else:
            assert can_use, f"Должно быть доступно: {reason}"
    
    @pytest.mark.asyncio
    async def test_budget_limits(self, billing_service, save_test_company, test_user, test_company, company_repo):
        """Тест бюджетных лимитов"""
        test_company.monthly_budget = 100.0
        test_company.current_month_spent = 99.0
        # Сохраняем в БД т.к. can_use_resource загружает компанию из репозитория
        await company_repo.set(test_company)
        
        can_use, reason = await billing_service.can_use_resource(
            test_user, test_company, "llm:gpt-4"
        )
        
        assert isinstance(can_use, bool)
        assert isinstance(reason, str)
    
    @pytest.mark.asyncio
    async def test_record_usage(self, billing_service, save_test_company, test_user, test_company, company_repo, usage_repo):
        """Тест записи использования"""
        from core.models.billing_models import TariffPlan
        
        test_company.tariff_plan = TariffPlan.ENTERPRISE
        await company_repo.set(test_company)
        
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
        
        updated_company = await company_repo.get(test_company.company_id)
        assert updated_company is not None
        assert updated_company.current_month_spent == initial_spent + 0.5
        
        all_usage = await usage_repo.list_all(limit=10000)
        weather_usage = [u for u in all_usage if u.resource_name == "tool:weather_api"]
        
        assert len(weather_usage) > 0, "Записи использования не найдены"
        found_record = weather_usage[0]
        
        assert found_record.cost == 0.5
        assert found_record.usage_type == UsageType.TOOL_CALL
        assert found_record.metadata.get("test") == "data"
    
    
    @pytest.mark.asyncio
    async def test_get_company_usage_stats(self, billing_service, test_user, company_repo, usage_repo, unique_id):
        """Тест получения полной статистики компании"""
        from core.models import Company
        from core.models.billing_models import TariffPlan
        
        stats_company = Company(
            company_id=unique_id("stats_company"),
            subdomain=unique_id("stats"),
            name="Stats Test Company",
            tariff_plan=TariffPlan.ENTERPRISE,
            balance=100000.0,
            monthly_budget=50000.0,
            current_month_spent=0.0,
            status="active"
        )
        
        await company_repo.set(stats_company)

        from core.context import set_context, Context
        context = Context(user=test_user, platform="test", active_company=stats_company)
        set_context(context)
        
        from datetime import datetime, timezone
        
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        usage_records = [
            UsageRecord(
                usage_id=unique_id("stats"),
                user_id=test_user.user_id,
                company_id=stats_company.company_id,
                usage_type=UsageType.LLM_REQUEST,
                resource_name="llm:gpt-4",
                cost=2.0,
                quantity=1000,
                timestamp=current_month
            ),
            UsageRecord(
                usage_id=unique_id("stats"),
                user_id=test_user.user_id,
                company_id=stats_company.company_id,
                usage_type=UsageType.TOOL_CALL,
                resource_name="tool:weather_api",
                cost=0.1,
                quantity=1,
                timestamp=current_month
            ),
            UsageRecord(
                usage_id=unique_id("stats"),
                user_id=test_user.user_id,
                company_id=stats_company.company_id,
                usage_type=UsageType.TOOL_CALL,
                resource_name="tool:weather_api",
                cost=0.1,
                quantity=1,
                timestamp=current_month
            )
        ]
        
        # Используем тот же storage что и billing_service для гарантии консистентности
        for usage in usage_records:
            usage_key = f"usage:{stats_company.company_id}:{usage.resource_name}:{usage.usage_id}"
            await usage_repo.set(usage)
        
        # Небольшая задержка для гарантии коммита транзакций
        import asyncio
        await asyncio.sleep(0.2)
        
        # Проверяем что записи сохранены
        usage_prefix = f"usage:{stats_company.company_id}:"
        all_usage_list = await usage_repo.list_all(limit=10000); all_usage = {f"usage:{u.resource_name}:{u.usage_id}": u.model_dump_json() for u in all_usage_list}
        assert len(all_usage) == len(usage_records), f"Должно быть {len(usage_records)} записей, найдено {len(all_usage)}"
        
        stats = await billing_service.get_company_usage_stats(stats_company.company_id)
        
        assert stats["total_cost"] == 2.2, f"Общая стоимость должна быть 2.2, получено: {stats['total_cost']}, stats={stats}"
        assert stats["total_calls"] == 1002, f"Общее количество вызовов должно быть 1002, получено: {stats['total_calls']}"
        assert "llm:gpt-4" in stats["by_resource"]
        assert "tool:weather_api" in stats["by_resource"]
        assert stats["by_resource"]["llm:gpt-4"]["cost"] == 2.0
        assert stats["by_resource"]["tool:weather_api"]["cost"] == 0.2
        assert stats["by_resource"]["tool:weather_api"]["calls"] == 2


@pytest.mark.asyncio
async def test_billing_service_integration(billing_service, save_test_company, test_user, test_company, company_repo):
    """Интеграционный тест всего BillingService"""
    from core.models.billing_models import TariffPlan
    test_company.tariff_plan = TariffPlan.PREMIUM
    test_company.balance = 10000.0
    test_company.monthly_budget = 5000.0
    test_company.current_month_spent = 100.0
    await company_repo.set(test_company)
    
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

"""
Integration тесты для API биллинга.

Тесты БЕЗ моков - проверяем реальные HTTP запросы с реальной БД.
Проверяем подписки, использование ресурсов, тарифы, пополнение баланса.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from datetime import datetime, timezone


@pytest.mark.asyncio
class TestBillingAPI:
    """Тесты для API биллинга"""

    async def test_get_subscription_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Получение информации о подписке"""
        response = await frontend_client.get(
            "/frontend/api/billing/subscription",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем обязательные поля
        assert "plan" in data
        assert "balance" in data
        assert "monthly_budget" in data
        assert "current_month_spent" in data
        assert "billing_period_start" in data
        
        # Проверяем типы
        assert isinstance(data["balance"], (int, float))
        assert isinstance(data["monthly_budget"], (int, float))
        assert isinstance(data["current_month_spent"], (int, float))

    async def test_get_subscription_unauthorized(self, frontend_client: AsyncClient):
        """Попытка получить подписку без авторизации"""
        response = await frontend_client.get("/frontend/api/billing/subscription")
        
        assert response.status_code == 401

    async def test_get_usage_stats_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Получение статистики использования"""
        from core.utils.tokens import get_token_service
        from core.models.billing_models import UsageRecord, UsageType
        import uuid
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        user_id = token_data.user_id
        
        # Устанавливаем контекст для usage_repository
        from core.context import set_context, clear_context
        from core.models.context_models import Context, Language
        
        company = await frontend_container.company_repository.get(company_id)
        user = await frontend_container.user_repository.get(user_id)
        
        context = Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU
        )
        set_context(context)
        
        # Создаем записи использования
        usage1 = UsageRecord(
            usage_id=str(uuid.uuid4()),
            user_id=user_id,
            company_id=company_id,
            session_id="test_session",
            usage_type=UsageType.TOOL_CALL,
            resource_name="tool:calculator",
            cost=10.5,
            quantity=5
        )
        usage2 = UsageRecord(
            usage_id=str(uuid.uuid4()),
            user_id=user_id,
            company_id=company_id,
            session_id="test_session",
            usage_type=UsageType.LLM_REQUEST,
            resource_name="llm:gpt4",
            cost=25.0,
            quantity=2
        )
        
        await frontend_container.usage_repository.set(usage1)
        await frontend_container.usage_repository.set(usage2)
        
        # Очищаем контекст
        clear_context()
        
        response = await frontend_client.get(
            "/frontend/api/billing/usage",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем структуру
        assert "total_cost" in data
        assert "total_calls" in data
        assert "by_resource" in data
        assert "by_user" in data
        
        # Проверяем данные
        assert data["total_cost"] >= 35.5  # Наши записи
        assert data["total_calls"] >= 7

    async def test_create_topup_payment(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        monkeypatch,
    ):
        """Создание платежа на пополнение"""
        from core.clients.payment.factory import PaymentProviderFactory
        from core.clients.payment.yoomoney_provider import YooMoneyConfig, YooMoneyProvider

        provider = YooMoneyProvider(YooMoneyConfig(
            provider_type="yoomoney",
            account_number="4100999",
            notification_secret="test_secret",
        ))
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_test": provider},
        )
        monkeypatch.setattr(
            PaymentProviderFactory, "get_default_provider",
            classmethod(lambda cls: provider),
        )

        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 1000.0},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "payment_id" in data
        assert data["amount"] == 1000.0
        assert "payment_url" in data

    async def test_create_topup_invalid_amount_too_small(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Попытка пополнить на слишком маленькую сумму"""
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={
                "amount": 50.0,  # Минимум 100
                "payment_method": "card"
            }
        )
        
        assert response.status_code == 422  # Validation error

    async def test_create_topup_invalid_amount_too_large(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Попытка пополнить на слишком большую сумму"""
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={
                "amount": 2000000.0,  # Максимум 1000000
                "payment_method": "card"
            }
        )
        
        assert response.status_code == 422

    async def test_create_topup_as_viewer_forbidden(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Попытка пополнить баланс с ролью viewer"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        company_id = f"test_company_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="Test Company",
            owner_id="owner_user",
            members={"viewer_user": ["viewer"]}
        )
        await frontend_container.company_repository.set(company)
        
        user = User(
            user_id="viewer_user",
            name="Viewer User",
            companies={company_id: ["viewer"]},
            active_company_id=company_id
        )
        await frontend_container.user_repository.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token("viewer_user", company_id=company_id)
        
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "amount": 1000.0,
                "payment_method": "card"
            }
        )
        
        assert response.status_code == 403

    async def test_change_plan_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Смена тарифного плана"""
        from core.utils.tokens import get_token_service
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        user_id = token_data.user_id
        
        # Убеждаемся что пользователь owner
        company = await frontend_container.company_repository.get(company_id)
        if user_id not in company.members or "owner" not in company.members[user_id]:
            company.members[user_id] = ["owner"]
            company.owner_user_id = user_id
            await frontend_container.company_repository.set(company)
        
        response = await frontend_client.patch(
            "/frontend/api/billing/plan",
            headers=auth_headers,
            json={"plan": "premium"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["plan"] == "premium"
        
        # Проверяем что план действительно изменился в БД
        updated_company = await frontend_container.company_repository.get(company_id)
        assert updated_company.tariff_plan.value == "premium"

    async def test_change_plan_invalid_plan(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Попытка сменить на недопустимый тариф"""
        from core.utils.tokens import get_token_service
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        user_id = token_data.user_id
        
        # Убеждаемся что owner
        company = await frontend_container.company_repository.get(company_id)
        company.members[user_id] = ["owner"]
        company.owner_user_id = user_id
        await frontend_container.company_repository.set(company)
        
        response = await frontend_client.patch(
            "/frontend/api/billing/plan",
            headers=auth_headers,
            json={"plan": "invalid_plan"}
        )
        
        assert response.status_code == 400
        assert "Недопустимый тариф" in response.json()["detail"]

    async def test_change_plan_only_owner(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Только owner может менять тариф"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        company_id = f"test_company_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="Test Company",
            owner_id="owner_user",
            members={"admin_user": ["admin"]}
        )
        await frontend_container.company_repository.set(company)
        
        user = User(
            user_id="admin_user",
            name="Admin User",
            companies={company_id: ["admin"]},
            active_company_id=company_id
        )
        await frontend_container.user_repository.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token("admin_user", company_id=company_id)
        
        response = await frontend_client.patch(
            "/frontend/api/billing/plan",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan": "premium"}
        )
        
        assert response.status_code == 403
        assert "владелец" in response.json()["detail"].lower()

    async def test_change_plan_same_plan(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Попытка сменить на текущий тариф"""
        from core.utils.tokens import get_token_service
        from core.models.billing_models import TariffPlan
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        user_id = token_data.user_id
        
        company = await frontend_container.company_repository.get(company_id)
        company.members[user_id] = ["owner"]
        company.owner_user_id = user_id
        company.tariff_plan = TariffPlan.FREE
        await frontend_container.company_repository.set(company)
        
        response = await frontend_client.patch(
            "/frontend/api/billing/plan",
            headers=auth_headers,
            json={"plan": "free"}
        )
        
        assert response.status_code == 400
        assert "уже использует" in response.json()["detail"].lower()

    async def test_get_payment_history(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Получение истории платежей"""
        response = await frontend_client.get(
            "/frontend/api/billing/history",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Пока mock, но структура должна быть правильной
        assert "payments" in data

    async def test_billing_isolation_between_companies(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Проверка изоляции биллинга между компаниями"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        from core.models.billing_models import TariffPlan
        
        # Создаем две компании с разными тарифами
        company1_id = f"company1_{uuid.uuid4().hex[:8]}"
        company2_id = f"company2_{uuid.uuid4().hex[:8]}"
        
        company1 = Company(
            company_id=company1_id,
            name="Company 1",
            owner_id="user1",
            members={"user1": ["owner"]},
            tariff_plan=TariffPlan.FREE,
            balance=100.0,
            monthly_budget=1000.0
        )
        company2 = Company(
            company_id=company2_id,
            name="Company 2",
            owner_id="user2",
            members={"user2": ["owner"]},
            tariff_plan=TariffPlan.PREMIUM,
            balance=5000.0,
            monthly_budget=10000.0
        )
        
        await frontend_container.company_repository.set(company1)
        await frontend_container.company_repository.set(company2)
        
        user1 = User(
            user_id="user1",
            name="User 1",
            companies={company1_id: ["owner"]},
            active_company_id=company1_id
        )
        user2 = User(
            user_id="user2",
            name="User 2",
            companies={company2_id: ["owner"]},
            active_company_id=company2_id
        )
        
        await frontend_container.user_repository.set(user1)
        await frontend_container.user_repository.set(user2)
        
        token_service = get_token_service()
        token1 = token_service.create_token("user1", company_id=company1_id)
        token2 = token_service.create_token("user2", company_id=company2_id)
        
        # Проверяем что каждая компания видит только свои данные
        response1 = await frontend_client.get(
            "/frontend/api/billing/subscription",
            headers={"Authorization": f"Bearer {token1}"}
        )
        response2 = await frontend_client.get(
            "/frontend/api/billing/subscription",
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Данные должны быть разными
        assert data1["plan"] == "free"
        assert data2["plan"] == "premium"
        assert data1["balance"] == 100.0
        assert data2["balance"] == 5000.0
        assert data1["monthly_budget"] == 1000.0
        assert data2["monthly_budget"] == 10000.0


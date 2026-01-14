"""
Integration тесты для API настроек.

Тесты БЕЗ моков - проверяем реальные HTTP запросы с реальной БД.
Проверяем управление настройками компании, безопасностью и интеграциями.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSettingsAPI:
    """Тесты для API настроек"""

    async def test_get_company_settings_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Получение настроек компании"""
        response = await frontend_client.get(
            "/frontend/api/settings/company",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем обязательные поля
        assert "company_id" in data
        assert "name" in data
        assert "subdomain" in data
        assert "status" in data
        assert "monthly_budget" in data
        assert "tariff_plan" in data
        assert "created_at" in data

    async def test_get_company_settings_unauthorized(self, frontend_client: AsyncClient):
        """Попытка получить настройки без авторизации"""
        response = await frontend_client.get("/frontend/api/settings/company")
        
        assert response.status_code == 401

    async def test_update_company_settings_name(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Обновление названия компании"""
        from core.utils.tokens import get_token_service
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        new_name = "Updated Company Name"
        
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"name": new_name}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["company"]["name"] == new_name
        
        # Проверяем что изменение сохранилось в БД
        company = await frontend_container.company_repository.get(company_id)
        assert company.name == new_name

    async def test_update_company_settings_monthly_budget(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Обновление месячного лимита"""
        from core.utils.tokens import get_token_service
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        new_budget = 5000.0
        
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"monthly_budget": new_budget}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["company"]["monthly_budget"] == new_budget
        
        # Проверяем БД
        company = await frontend_container.company_repository.get(company_id)
        assert company.monthly_budget == new_budget

    async def test_update_company_settings_negative_budget(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Попытка установить отрицательный лимит"""
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"monthly_budget": -1000.0}
        )
        
        assert response.status_code == 400
        assert "отрицательным" in response.json()["detail"].lower()

    async def test_update_company_settings_metadata(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Обновление метаданных компании"""
        from core.utils.tokens import get_token_service
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        metadata = {
            "custom_field": "value",
            "feature_flags": {"new_ui": True}
        }
        
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"metadata": metadata}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Проверяем БД
        company = await frontend_container.company_repository.get(company_id)
        assert "custom_field" in company.metadata
        assert company.metadata["custom_field"] == "value"

    async def test_update_company_settings_as_viewer_forbidden(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Попытка обновить настройки с ролью viewer"""
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
        
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "New Name"}
        )
        
        assert response.status_code == 403

    async def test_get_security_settings(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Получение настроек безопасности"""
        response = await frontend_client.get(
            "/frontend/api/settings/security",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "user_id" in data
        assert "active_sessions" in data
        assert "two_factor_enabled" in data
        assert "oauth_providers" in data
        assert isinstance(data["oauth_providers"], list)

    async def test_get_oauth_providers(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Получение списка OAuth провайдеров"""
        response = await frontend_client.get(
            "/frontend/api/settings/oauth-providers",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "providers" in data
        providers = data["providers"]
        
        # Должны быть все три провайдера
        provider_ids = [p["id"] for p in providers]
        assert "yandex" in provider_ids
        assert "google" in provider_ids
        assert "github" in provider_ids
        
        # Проверяем структуру
        for provider in providers:
            assert "id" in provider
            assert "name" in provider
            assert "enabled" in provider
            assert "icon" in provider

    async def test_get_integrations(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Получение настроек интеграций"""
        response = await frontend_client.get(
            "/frontend/api/settings/integrations",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "integrations" in data
        assert "available" in data
        assert isinstance(data["available"], list)

    async def test_settings_isolation_between_companies(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Проверка изоляции настроек между компаниями"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        # Создаем две компании с разными настройками
        company1_id = f"company1_{uuid.uuid4().hex[:8]}"
        company2_id = f"company2_{uuid.uuid4().hex[:8]}"
        
        company1 = Company(
            company_id=company1_id,
            name="Company 1",
            subdomain="company1",
            owner_id="user1",
            members={"user1": ["owner"]},
            monthly_budget=1000.0,
            metadata={"feature": "value1"}
        )
        company2 = Company(
            company_id=company2_id,
            name="Company 2",
            subdomain="company2",
            owner_id="user2",
            members={"user2": ["owner"]},
            monthly_budget=5000.0,
            metadata={"feature": "value2"}
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
        
        # Получаем настройки для каждой компании
        response1 = await frontend_client.get(
            "/frontend/api/settings/company",
            headers={"Authorization": f"Bearer {token1}"}
        )
        response2 = await frontend_client.get(
            "/frontend/api/settings/company",
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Данные должны быть разными
        assert data1["name"] == "Company 1"
        assert data2["name"] == "Company 2"
        assert data1["subdomain"] == "company1"
        assert data2["subdomain"] == "company2"
        assert data1["monthly_budget"] == 1000.0
        assert data2["monthly_budget"] == 5000.0
        assert data1["metadata"]["feature"] == "value1"
        assert data2["metadata"]["feature"] == "value2"

    async def test_update_all_settings_together(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Обновление всех настроек одновременно"""
        from core.utils.tokens import get_token_service
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={
                "name": "Fully Updated Company",
                "monthly_budget": 3000.0,
                "metadata": {"updated": True}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Проверяем БД
        company = await frontend_container.company_repository.get(company_id)
        assert company.name == "Fully Updated Company"
        assert company.monthly_budget == 3000.0
        assert "updated" in company.metadata
        assert company.metadata["updated"] is True


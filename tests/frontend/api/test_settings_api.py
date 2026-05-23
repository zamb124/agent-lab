"""
Integration тесты для API настроек.

Тесты БЕЗ моков - проверяем реальные HTTP запросы с реальной БД.
Проверяем управление настройками компании, безопасностью и интеграциями.
"""

import pytest
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
        """Получение профиля компании и снимка AI-провайдеров (раздельные роутеры)."""
        response = await frontend_client.get(
            "/frontend/api/settings/company",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "company_id" in data
        assert "name" in data
        assert "monthly_budget" in data

        ai = await frontend_client.get(
            "/frontend/api/settings/ai-providers",
            headers=auth_headers,
        )
        assert ai.status_code == 200
        body = ai.json()
        caps = {item["capability"]: item for item in body["capabilities"]}
        assert caps["embedding"]["kind"] == "embedding"
        assert caps["rerank"]["kind"] == "rerank"
        summarize = caps["llm_summarize"]
        assert summarize["kind"] == "llm"
        assert "llm_summarize" in body["catalog"]
        prov_items = body["catalog"]["llm_summarize"]
        assert any(p.get("kind") == "platform" for p in prov_items)
        assert body["llm_context"]["configured"] is False
        assert body["llm_context"]["config"] == {}
        assert "standard" in body["llm_context"]["profiles"]
        assert "large" in body["llm_context"]["budgets"]

    async def test_update_ai_provider_llm_context_default(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container
    ):
        """Company default контекстного слоя сохраняется в реальной БД и снимается DELETE."""
        from core.company_ai import CompanyAIProviders
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        payload = {
            "profile": "agent",
            "memory": "session",
            "retrieval": {"mode": "hybrid", "top_k": 24, "rerank": True},
            "budget": "large",
            "cache": "provider_hints",
        }
        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=auth_headers,
            json=payload,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        company = await frontend_container.company_repository.get(company_id)
        aip = CompanyAIProviders.from_metadata(company.metadata or {})
        assert aip.llm_context is not None
        assert aip.llm_context.profile == "agent"
        assert aip.llm_context.retrieval is not None
        assert aip.llm_context.retrieval.top_k == 24

        snapshot = await frontend_client.get(
            "/frontend/api/settings/ai-providers",
            headers=auth_headers,
        )
        assert snapshot.status_code == 200
        body = snapshot.json()["llm_context"]
        assert body["configured"] is True
        assert body["config"]["profile"] == "agent"
        assert body["config"]["retrieval"]["rerank"] is True

        cleared = await frontend_client.delete(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=auth_headers,
        )
        assert cleared.status_code == 200
        company = await frontend_container.company_repository.get(company_id)
        aip = CompanyAIProviders.from_metadata(company.metadata or {})
        assert aip.llm_context is None

    async def test_update_ai_provider_llm_context_rejects_unknown_profile(
        self,
        frontend_client: AsyncClient,
        auth_headers,
    ):
        """Company default валидируется против platform profiles сразу в Settings API."""
        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=auth_headers,
            json={"profile": "missing-profile"},
        )

        assert response.status_code == 400
        assert "missing-profile" in response.json()["detail"]

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

        from core.models.identity_models import Company, User
        from core.utils.tokens import get_token_service

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

    async def test_settings_isolation_between_companies(
        self,
        frontend_client: AsyncClient,
        frontend_container
    ):
        """Проверка изоляции настроек между компаниями"""
        import uuid

        from core.models.identity_models import Company, User
        from core.utils.tokens import get_token_service

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

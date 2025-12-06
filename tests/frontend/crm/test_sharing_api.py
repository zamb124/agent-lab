"""
Тесты для CRM Sharing API - поиск пользователей и компаний для shared_with.

Реальные интеграционные тесты без моков.

Данные для тестов создаются в session_test_data (conftest.py):
- Test Session Company - компания
- sharing_user_alice, sharing_user_bob, sharing_user_charlie - пользователи с email
"""

import pytest


class TestSharingSearchAPI:
    """Тесты поиска для shared_with"""
    
    @pytest.mark.asyncio
    async def test_search_users_by_email(self, crm_frontend_client, crm_server_process):
        """Поиск пользователей по email"""
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "alice.sharing"}
        )
        
        assert response.status_code == 200
        results = response.json()
        
        # Должен найти Alice
        user_results = [r for r in results if r["type"] == "user"]
        assert len(user_results) >= 1, f"Expected user, got: {results}"
        
        alice = next((r for r in user_results if "alice.sharing" in r.get("email", "").lower()), None)
        assert alice is not None, f"Alice not found in: {user_results}"
        assert alice["email"] == "alice.sharing@testmail.com"
    
    @pytest.mark.asyncio
    async def test_search_users_by_domain(self, crm_frontend_client, crm_server_process):
        """Поиск пользователей по домену email"""
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "testmail"}
        )
        
        assert response.status_code == 200
        results = response.json()
        
        # Должен найти всех трех пользователей с testmail.com
        user_results = [r for r in results if r["type"] == "user"]
        assert len(user_results) >= 3, f"Expected 3 users, got: {user_results}"
        
        emails = [r.get("email", "") for r in user_results]
        assert any("alice.sharing" in e for e in emails)
        assert any("bob.sharing" in e for e in emails)
        assert any("charlie.sharing" in e for e in emails)
    
    @pytest.mark.asyncio
    async def test_search_companies_by_name(self, crm_frontend_client, crm_server_process):
        """Поиск компаний по названию"""
        # Ищем Test Session Company - она создается в session_test_data
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "Session"}
        )
        
        assert response.status_code == 200
        results = response.json()
        
        company_results = [r for r in results if r["type"] == "company"]
        assert len(company_results) >= 1, f"Expected Session company, got: {results}"
        
        session_co = next((r for r in company_results if "Session" in r.get("name", "")), None)
        assert session_co is not None, f"Session company not found in: {company_results}"
        assert "members_count" in session_co
    
    @pytest.mark.asyncio
    async def test_search_returns_both_users_and_companies(self, crm_frontend_client, crm_server_process):
        """Поиск возвращает и пользователей и компании"""
        # Проверка users
        response_users = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "alice.sharing"}
        )
        assert response_users.status_code == 200
        user_results = [r for r in response_users.json() if r["type"] == "user"]
        assert len(user_results) >= 1
        
        # Проверка companies - Test Session Company
        response_companies = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "Session"}
        )
        assert response_companies.status_code == 200
        company_results = [r for r in response_companies.json() if r["type"] == "company"]
        assert len(company_results) >= 1, f"Expected Session company, got: {response_companies.json()}"
    
    @pytest.mark.asyncio
    async def test_search_minimum_query_length(self, crm_frontend_client, crm_server_process):
        """Поиск требует минимум 2 символа"""
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "a"}
        )
        
        # FastAPI validation error
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, crm_frontend_client, crm_server_process):
        """Поиск без результатов"""
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "nonexistent_query_xyz123"}
        )
        
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, crm_frontend_client, crm_server_process):
        """Поиск не зависит от регистра"""
        # Поиск с разным регистром
        response_lower = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "alice.sharing"}
        )
        response_upper = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "ALICE.SHARING"}
        )
        response_mixed = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "AlIcE.sHaRiNg"}
        )
        
        assert response_lower.status_code == 200
        assert response_upper.status_code == 200
        assert response_mixed.status_code == 200
        
        # Все должны найти alice
        def has_alice(results):
            return any("alice.sharing" in r.get("email", "").lower() for r in results if r["type"] == "user")
        
        assert has_alice(response_lower.json())
        assert has_alice(response_upper.json())
        assert has_alice(response_mixed.json())
    
    @pytest.mark.asyncio
    async def test_search_results_limit(self, crm_frontend_client, crm_server_process):
        """Поиск ограничен 20 результатами"""
        # Поиск по общему паттерну
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "sharing"}
        )
        
        assert response.status_code == 200
        results = response.json()
        
        # Не более 20 результатов
        assert len(results) <= 20
    
    @pytest.mark.asyncio
    async def test_user_result_structure(self, crm_frontend_client, crm_server_process):
        """Структура результата для пользователя"""
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "alice.sharing"}
        )
        
        assert response.status_code == 200
        results = response.json()
        
        user_results = [r for r in results if r["type"] == "user"]
        assert len(user_results) >= 1
        
        user = user_results[0]
        assert "type" in user
        assert user["type"] == "user"
        assert "id" in user
        assert "email" in user
    
    @pytest.mark.asyncio
    async def test_company_result_structure(self, crm_frontend_client, crm_server_process):
        """Структура результата для компании"""
        # Ищем Test Session Company
        response = await crm_frontend_client.get(
            "/crm/api/sharing/search",
            params={"q": "Session"}
        )
        
        assert response.status_code == 200
        results = response.json()
        
        company_results = [r for r in results if r["type"] == "company"]
        assert len(company_results) >= 1, f"Expected Session company, got: {results}"
        
        company = company_results[0]
        assert "type" in company
        assert company["type"] == "company"
        assert "id" in company
        assert "name" in company
        assert "members_count" in company

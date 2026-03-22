"""
Интеграционные тесты для эндпоинта /flows/api/auth/me на agents сервисе.

Проверяем что эндпоинт доступен и работает корректно на agents service,
используя тот же core роутер что и в frontend.
"""

import time
import pytest
import jwt
from core.config import get_settings


class TestAuthMeAgents:
    """Интеграционные тесты /flows/api/auth/me для agents сервиса"""
    
    @pytest.mark.asyncio
    async def test_auth_me_success_agents(self, flows_client, auth_token):
        """Успешный запрос к agents сервису с валидным токеном"""
        response = await flows_client.get(
            "/flows/api/auth/me",
            cookies={"auth_token": auth_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "user_id" in data
        assert "company_id" in data
        assert "roles" in data
        assert isinstance(data["roles"], list)
        
        print(f"✅ Agents: /api/auth/me успешно вернул данные: user_id={data['user_id']}")
    
    @pytest.mark.asyncio
    async def test_auth_me_no_token_agents(self, flows_client):
        """Запрос к agents без токена возвращает 401"""
        response = await flows_client.get("/flows/api/auth/me")
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        
        print("✅ Agents: /api/auth/me без токена корректно возвращает 401")
    
    @pytest.mark.asyncio
    async def test_auth_me_invalid_token_agents(self, flows_client):
        """Невалидный токен на agents возвращает 401"""
        response = await flows_client.get(
            "/flows/api/auth/me",
            cookies={"auth_token": "invalid.token.here"}
        )
        
        assert response.status_code == 401
        print("✅ Agents: /api/auth/me с невалидным токеном корректно возвращает 401")
    
    @pytest.mark.asyncio
    async def test_auth_me_expired_token_agents(self, flows_client):
        """Истекший токен на agents возвращает 401"""
        settings = get_settings()
        
        expired_token = jwt.encode(
            {
                "user_id": "test_user",
                "company_id": "test_company",
                "roles": ["user"],
                "exp": int(time.time()) - 3600
            },
            settings.auth.jwt_secret_key,
            algorithm="HS256"
        )
        
        response = await flows_client.get(
            "/flows/api/auth/me",
            cookies={"auth_token": expired_token}
        )
        
        assert response.status_code == 401
        print("✅ Agents: /api/auth/me с истекшим токеном корректно возвращает 401")
    
    @pytest.mark.asyncio
    async def test_auth_me_response_structure_agents(self, flows_client, auth_token):
        """Проверка структуры ответа на agents сервисе"""
        response = await flows_client.get(
            "/flows/api/auth/me",
            cookies={"auth_token": auth_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["user_id", "company_id", "roles"]
        for field in required_fields:
            assert field in data, f"Поле {field} отсутствует в ответе"
        
        assert isinstance(data["roles"], list), "roles должен быть списком"
        
        print("✅ Agents: /api/auth/me возвращает корректную структуру данных")
    
    @pytest.mark.asyncio
    async def test_auth_me_consistency_between_services(
        self, 
        flows_client, 
        frontend_client, 
        auth_token
    ):
        """Единый контракт ответа между frontend и agents сервисами"""
        agents_response = await flows_client.get(
            "/flows/api/auth/me",
            cookies={"auth_token": auth_token}
        )
        
        frontend_response = await frontend_client.get(
            "/frontend/api/auth/me",
            cookies={"auth_token": auth_token}
        )
        
        assert agents_response.status_code == 200
        assert frontend_response.status_code == 200
        
        agents_data = agents_response.json()
        frontend_data = frontend_response.json()
        
        assert set(agents_data.keys()) == set(frontend_data.keys()), \
            "Структура ответа должна быть одинаковой на всех сервисах"
        
        assert agents_data["user_id"] == frontend_data["user_id"]
        assert agents_data["company_id"] == frontend_data["company_id"]
        assert agents_data["roles"] == frontend_data["roles"]
        
        print("✅ /api/auth/me возвращает единый контракт на frontend и agents")


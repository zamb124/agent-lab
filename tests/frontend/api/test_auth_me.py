"""
Интеграционные тесты для эндпоинта /api/auth/me.

Тестируем без моков:
- Реальная БД (PostgreSQL)
- Реальный TokenService для генерации JWT
- Реальный AuthMiddleware для валидации
- HTTP клиент делает настоящие запросы к FastAPI приложению
"""

import time
import pytest
import jwt
from core.config import get_settings


class TestAuthMeFrontend:
    """Интеграционные тесты /api/auth/me для frontend сервиса"""
    
    @pytest.mark.asyncio
    async def test_auth_me_success(self, frontend_client, auth_token):
        """Успешный запрос с валидным токеном"""
        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get("/frontend/api/auth/me")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "user_id" in data
        assert "company_id" in data
        assert "roles" in data
        assert isinstance(data["roles"], list)
        
        print(f"✅ /api/auth/me успешно вернул данные: user_id={data['user_id']}")
    
    @pytest.mark.asyncio
    async def test_auth_me_no_token(self, frontend_client):
        """Запрос без токена возвращает 401"""
        response = await frontend_client.get("/frontend/api/auth/me")
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        
        print("✅ /api/auth/me без токена корректно возвращает 401")
    
    @pytest.mark.asyncio
    async def test_auth_me_invalid_token(self, frontend_client):
        """Невалидный токен возвращает 401"""
        frontend_client.cookies.set("auth_token", "invalid.token.here")
        response = await frontend_client.get("/frontend/api/auth/me")
        
        assert response.status_code == 401
        print("✅ /api/auth/me с невалидным токеном корректно возвращает 401")
    
    @pytest.mark.asyncio
    async def test_auth_me_expired_token(self, frontend_client):
        """Истекший токен возвращает 401"""
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
        
        frontend_client.cookies.set("auth_token", expired_token)
        response = await frontend_client.get("/frontend/api/auth/me")
        
        assert response.status_code == 401
        print("✅ /api/auth/me с истекшим токеном корректно возвращает 401")
    
    @pytest.mark.asyncio
    async def test_auth_me_with_subdomain(
        self, frontend_client, auth_token, frontend_container
    ):
        """Запрос с субдоменом: Host должен соответствовать маппингу компании в storage."""
        from core.utils.tokens import get_token_service

        frontend_client.cookies.set("auth_token", auth_token)
        token_service = get_token_service()
        td = token_service.validate_token(auth_token)
        if td is None or not td.company_id:
            raise AssertionError("auth_token: ожидается валидный company_id")
        company = await frontend_container.company_repository.get(td.company_id)
        if company is None or not company.subdomain:
            raise AssertionError("Компания из токена с subdomain")
        response = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={"Host": f"{company.subdomain}.localhost:8002"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # company_id может быть None или пустой строкой, если пользователь еще не выбрал компанию
        assert "company_id" in data
        print(f"✅ /api/auth/me работает с субдоменом, company_id={data['company_id']}")
    
    @pytest.mark.asyncio
    async def test_auth_me_response_structure(self, frontend_client, auth_token):
        """Проверка структуры ответа"""
        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get("/frontend/api/auth/me")
        
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["user_id", "company_id", "roles"]
        for field in required_fields:
            assert field in data, f"Поле {field} отсутствует в ответе"
        
        assert isinstance(data["roles"], list), "roles должен быть списком"
        
        optional_fields = ["email", "name"]
        for field in optional_fields:
            if field in data:
                assert isinstance(data[field], (str, type(None))), f"{field} должен быть строкой или null"
        
        print("✅ /api/auth/me возвращает корректную структуру данных")
    
    @pytest.mark.asyncio
    async def test_auth_me_no_subdomain_allowed(self, frontend_client, auth_token):
        """Эндпоинт доступен без субдомена (пользователь может быть авторизован без выбранной компании)"""
        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={"Host": "localhost:8002"},
        )
        
        assert response.status_code == 200
        print("✅ /api/auth/me доступен без субдомена")


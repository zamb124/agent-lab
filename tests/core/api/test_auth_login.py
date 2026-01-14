"""
Тесты для эндпоинта /frontend/api/auth/login/{provider_name}
"""
import pytest


@pytest.mark.asyncio
class TestAuthLogin:
    """Тесты для /frontend/api/auth/login/{provider} - проверяем что возвращается JSON, а не редирект"""
    
    async def test_login_returns_json_not_redirect(self, frontend_client):
        """Проверяем что login возвращает JSON с auth_url, а не редирект"""
        response = await frontend_client.get("/frontend/api/auth/login/yandex")
        
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "provider" in data
        assert data["provider"] == "yandex"
        assert "oauth.yandex.ru" in data["auth_url"]
        
        print(f"✅ /frontend/api/auth/login/yandex возвращает JSON с auth_url: {data['auth_url'][:80]}...")
    
    async def test_login_with_custom_host(self, frontend_client):
        """Проверяем что redirect_uri определяется из Host header"""
        response = await frontend_client.get(
            "/frontend/api/auth/login/yandex",
            headers={"host": "custom.domain.com"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        # redirect_uri должен быть на custom.domain.com
        assert "custom.domain.com" in data["auth_url"]
        
        print(f"✅ redirect_uri определяется из Host header: custom.domain.com")
    
    async def test_login_invalid_provider(self, frontend_client):
        """Проверяем обработку невалидного провайдера"""
        response = await frontend_client.get("/frontend/api/auth/login/invalid_provider")
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Неподдерживаемый провайдер" in data["detail"]
        
        print("✅ Невалидный провайдер корректно возвращает 400")
    
    async def test_login_protocol_detection(self, frontend_client):
        """Проверяем определение протокола (http/https) из запроса"""
        # По умолчанию testserver использует https
        response = await frontend_client.get("/frontend/api/auth/login/yandex")
        assert response.status_code == 200
        data = response.json()
        # redirect_uri в auth_url должен быть https
        assert "https%3A%2F%2Ftestserver" in data["auth_url"] or "https://testserver" in data["auth_url"]
        
        print("✅ Протокол по умолчанию: https")
        
        # С X-Forwarded-Proto=http должен использовать http
        response = await frontend_client.get(
            "/frontend/api/auth/login/yandex",
            headers={"x-forwarded-proto": "http"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "http%3A%2F%2Ftestserver" in data["auth_url"] or "http://testserver" in data["auth_url"]
        
        print("✅ X-Forwarded-Proto=http корректно переключает на http")



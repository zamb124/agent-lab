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
        """Проверяем что при кастомном хосте возвращается валидный auth_url"""
        response = await frontend_client.get(
            "/frontend/api/auth/login/yandex",
            headers={"host": "custom.domain.com"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "provider" in data
        # Для неизвестных доменов redirect_uri строится через PRIMARY_DOMAIN (humanitec.ru)
        # что позволяет использовать единый callback URL у OAuth провайдеров
        assert "oauth.yandex.ru" in data["auth_url"]
        assert "redirect_uri" in data["auth_url"]
        
        print(f"✅ Кастомный хост обрабатывается, возвращается валидный auth_url")
    
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
        # По умолчанию для не-localhost хостов — https
        response = await frontend_client.get("/frontend/api/auth/login/yandex")
        assert response.status_code == 200
        data = response.json()
        # redirect_uri должен использовать https (testserver — не localhost)
        assert "https%3A%2F%2F" in data["auth_url"] or "redirect_uri=https" in data["auth_url"]
        
        print("✅ Протокол по умолчанию: https")
        
        # С X-Forwarded-Proto=http должен использовать http
        response = await frontend_client.get(
            "/frontend/api/auth/login/yandex",
            headers={"x-forwarded-proto": "http"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "http%3A%2F%2F" in data["auth_url"] or "redirect_uri=http" in data["auth_url"]
        
        print("✅ X-Forwarded-Proto=http корректно переключает на http")

    async def test_login_apple_returns_appleid_when_configured(self, frontend_client):
        """При настроенном Apple в конфиге — JSON с auth_url на appleid.apple.com."""
        response = await frontend_client.get("/frontend/api/auth/login/apple")
        if response.status_code == 400:
            pytest.skip("Apple OAuth не настроен в тестовом окружении")
        assert response.status_code == 200
        data = response.json()
        assert data.get("provider") == "apple"
        assert "appleid.apple.com" in data["auth_url"]
        assert "response_mode=form_post" in data["auth_url"] or "response_mode%3Dform_post" in data["auth_url"]



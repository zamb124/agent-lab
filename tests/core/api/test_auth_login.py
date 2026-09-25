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

    async def test_login_linnex_redirect_uri(self, frontend_client):
        """OAuth redirect_uri на linnex.io для Host linnex.io."""
        response = await frontend_client.get(
            "/frontend/api/auth/login/yandex",
            headers={"host": "linnex.io"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "redirect_uri=https%3A%2F%2Flinnex.io" in data["auth_url"]

    async def test_login_unknown_host_rejected(self, frontend_client):
        """Неизвестный Host не должен получать OAuth redirect_uri."""
        response = await frontend_client.get(
            "/frontend/api/auth/login/yandex",
            headers={"host": "custom.domain.com"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "unsupported host domain" in data["detail"]

    async def test_login_invalid_provider(self, frontend_client):
        """Проверяем обработку невалидного провайдера"""
        response = await frontend_client.get("/frontend/api/auth/login/invalid_provider")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Unsupported provider" in data["detail"]

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
        assert response.status_code == 200, (
            "Ожидался JSON Apple login (200); при 400 проверьте конфиг Apple OAuth в тестовом окружении. "
            f"Ответ: {response.text}"
        )
        data = response.json()
        assert data.get("provider") == "apple"
        assert "appleid.apple.com" in data["auth_url"]
        assert "response_mode=form_post" in data["auth_url"] or "response_mode%3Dform_post" in data["auth_url"]

    async def test_login_apple_linnex_client_id(self, frontend_client):
        """Apple OAuth client_id per-brand для Host linnex.io."""
        response = await frontend_client.get(
            "/frontend/api/auth/login/apple",
            headers={"host": "linnex.io"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data.get("provider") == "apple"
        assert "client_id=app.linnex.io" in data["auth_url"] or "client_id%3Dapp.linnex.io" in data["auth_url"]



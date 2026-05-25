"""
Тесты демо-входа (auth.demo): статус, отказ GET /login/demo, POST при выключенном демо, успешный сценарий.
"""

import pytest

from core.config import get_settings, set_settings
from core.config.models import DemoAuthConfig
from core.identity.demo_bootstrap import ensure_demo_company_and_user


@pytest.mark.asyncio
class TestDemoAuth:
    async def test_get_login_demo_rejected(self, frontend_client):
        response = await frontend_client.get("/frontend/api/auth/login/demo")
        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "POST" in detail or "password" in detail.lower()

    async def test_demo_status_when_disabled(self, frontend_client):
        old = get_settings()
        demo_off = old.auth.model_copy(
            update={"demo": old.auth.demo.model_copy(update={"login_enabled": False})}
        )
        new_settings = old.model_copy(update={"auth": demo_off})
        set_settings(new_settings)
        try:
            response = await frontend_client.get("/frontend/api/auth/demo/status")
            assert response.status_code == 200
            data = response.json()
            assert data.get("enabled") is False
            assert "email" not in data
        finally:
            set_settings(old)

    async def test_login_demo_when_disabled_returns_401(self, frontend_client):
        old = get_settings()
        demo_off = old.auth.model_copy(
            update={"demo": old.auth.demo.model_copy(update={"login_enabled": False})}
        )
        new_settings = old.model_copy(update={"auth": demo_off})
        set_settings(new_settings)
        try:
            response = await frontend_client.post(
                "/frontend/api/auth/login/demo",
                json={"email": "demo@demo.ru", "password": "any"},
            )
            assert response.status_code == 401
        finally:
            set_settings(old)

    async def test_demo_login_success(self, unique_id, frontend_client):
        old = get_settings()
        subdomain = f"d{unique_id}"
        demo_cfg = DemoAuthConfig(
            login_enabled=True,
            password="integration_demo_pw_9xK",
            email=f"demoint_{unique_id}@demo.ru",
            company_id=f"demo_co_{unique_id}",
            subdomain=subdomain,
            company_name="Demo Integration",
        )
        new_auth = old.auth.model_copy(update={"demo": demo_cfg})
        new_settings = old.model_copy(update={"auth": new_auth})
        set_settings(new_settings)
        try:
            from apps.frontend.container import get_frontend_container

            container = get_frontend_container()
            await ensure_demo_company_and_user(
                company_repository=container.company_repository,
                user_repository=container.user_repository,
                subdomain_repository=container.subdomain_repository,
            )

            response = await frontend_client.post(
                "/frontend/api/auth/login/demo",
                json={
                    "email": demo_cfg.email,
                    "password": demo_cfg.password,
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload.get("success") is True
            assert "redirect_url" in payload
            assert subdomain in payload["redirect_url"]
            cookie_headers = [
                v
                for k, v in response.headers.multi_items()
                if k.lower() == "set-cookie"
            ]
            assert any("session_id=" in c for c in cookie_headers)
            assert any("auth_token=" in c for c in cookie_headers)
        finally:
            set_settings(old)

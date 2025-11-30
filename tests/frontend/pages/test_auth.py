"""
Тесты для страниц авторизации.

Используется реальная БД без моков.
"""

import pytest


class TestAuthPages:
    """Тесты для страниц авторизации"""
    
    @pytest.mark.asyncio
    async def test_auth_page(self, frontend_client):
        """Проверяем страницу авторизации"""
        response = await frontend_client.get("/frontend/auth")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_select_company_page(self, frontend_client):
        """Проверяем страницу выбора компании"""
        response = await frontend_client.get("/frontend/select-company")
        
        # Может быть 200 или редирект на create-company
        assert response.status_code in [200, 302, 307]
    
    @pytest.mark.asyncio
    async def test_create_company_page(self, frontend_client):
        """Проверяем страницу создания компании"""
        response = await frontend_client.get("/frontend/create-company")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

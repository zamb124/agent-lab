"""
Тесты для страниц dashboard.

Используется реальная БД без моков.
"""

import pytest


class TestDashboardPages:
    """Тесты для страниц dashboard"""
    
    @pytest.mark.asyncio
    async def test_index_page(self, frontend_client):
        """Проверяем индексную страницу"""
        response = await frontend_client.get("/frontend/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_dashboard_page(self, frontend_client):
        """Проверяем главную страницу dashboard"""
        response = await frontend_client.get("/frontend/dashboard")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_dashboard_welcome(self, frontend_client):
        """Проверяем приветственное сообщение"""
        response = await frontend_client.get("/frontend/dashboard/welcome")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_fashn_page(self, frontend_client):
        """Проверяем страницу FASHN"""
        response = await frontend_client.get("/frontend/fashn")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

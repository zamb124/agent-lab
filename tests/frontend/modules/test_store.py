"""
Тесты для модуля Store (магазин flows).

Используется реальная БД без моков.
"""

import pytest


class TestStorePageRoutes:
    """Тесты для страниц Store"""
    
    @pytest.mark.asyncio
    async def test_store_main_page(self, frontend_client):
        """Проверяем главную страницу Store"""
        response = await frontend_client.get("/frontend/store/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_store_list(self, frontend_client):
        """Проверяем список публичных flows"""
        response = await frontend_client.get("/frontend/store/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

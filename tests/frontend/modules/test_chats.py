"""
Тесты для модуля Chats (страницы чатов).

Используется реальная БД без моков.
"""

import pytest


class TestChatsPageRoutes:
    """Тесты для страниц Chats"""
    
    @pytest.mark.asyncio
    async def test_chats_main_page(self, frontend_client):
        """Проверяем главную страницу чатов"""
        response = await frontend_client.get("/frontend/chats/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_chats_list(self, frontend_client):
        """Проверяем список чатов"""
        response = await frontend_client.get("/frontend/chats/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_chats_list_with_filters(self, frontend_client):
        """Проверяем список чатов с фильтрами"""
        response = await frontend_client.get(
            "/frontend/chats/list?platform=test&limit=10"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

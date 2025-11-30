"""
Тесты для модуля Abilities (страницы способностей).

Используется реальная БД без моков.
"""

import pytest


class TestAbilitiesPageRoutes:
    """Тесты для страниц Abilities"""
    
    @pytest.mark.asyncio
    async def test_abilities_main_page(self, frontend_client):
        """Проверяем главную страницу способностей"""
        response = await frontend_client.get("/frontend/abilities/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_abilities_list(self, frontend_client):
        """Проверяем список способностей"""
        response = await frontend_client.get("/frontend/abilities/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

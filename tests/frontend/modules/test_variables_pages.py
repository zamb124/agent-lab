"""
Тесты для модуля Variables (страницы управления переменными).

Используется реальная БД без моков.
"""

import pytest


class TestVariablesPageRoutes:
    """Тесты для страниц Variables"""
    
    @pytest.mark.asyncio
    async def test_variables_main_page(self, frontend_client):
        """Проверяем главную страницу переменных"""
        response = await frontend_client.get("/frontend/variables/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_variables_list(self, frontend_client):
        """Проверяем список переменных"""
        response = await frontend_client.get("/frontend/variables/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

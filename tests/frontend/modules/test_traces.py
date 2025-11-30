"""
Тесты для модуля Traces (страницы трейсов OpenTelemetry).

Используется реальная БД без моков.
"""

import pytest


class TestTracesPageRoutes:
    """Тесты для страниц Traces"""
    
    @pytest.mark.asyncio
    async def test_traces_main_page(self, frontend_client):
        """Проверяем главную страницу трейсов"""
        response = await frontend_client.get("/frontend/traces/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_traces_list(self, frontend_client):
        """Проверяем таблицу трейсов"""
        response = await frontend_client.get("/frontend/traces/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_traces_list_with_filters(self, frontend_client):
        """Проверяем таблицу с фильтрами"""
        response = await frontend_client.get(
            "/frontend/traces/list?status=ok&limit=10"
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_trace_detail_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего трейса"""
        response = await frontend_client.get("/frontend/traces/nonexistent")
        
        assert response.status_code == 404

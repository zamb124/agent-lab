"""
Тесты для модуля Billing (страницы биллинга).

Используется реальная БД без моков.
"""

import pytest


class TestBillingPageRoutes:
    """Тесты для страниц Billing"""
    
    @pytest.mark.asyncio
    async def test_billing_main_page(self, frontend_client):
        """Проверяем главную страницу биллинга"""
        response = await frontend_client.get("/frontend/billing/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestBillingAPI:
    """Тесты для API биллинга"""
    
    @pytest.mark.asyncio
    async def test_billing_stats(self, frontend_client):
        """Проверяем API статистики"""
        response = await frontend_client.get("/frontend/billing/api/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "company_id" in data
        assert "tariff_plan" in data
    
    @pytest.mark.asyncio
    async def test_initiate_payment(self, frontend_client):
        """Проверяем API инициализации платежа"""
        response = await frontend_client.post(
            "/frontend/billing/api/payment",
            json={"amount": 1000}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["amount"] == 1000

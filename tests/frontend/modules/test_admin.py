"""
Тесты для модуля Admin (страницы администрирования).

Используется реальная БД без моков.
Требует прав system admin.
"""

import pytest


class TestAdminPageRoutes:
    """Тесты для страниц Admin"""
    
    @pytest.mark.asyncio
    async def test_admin_companies_requires_auth(self, frontend_client):
        """Проверяем что страница требует авторизации system admin"""
        response = await frontend_client.get("/frontend/admin/companies")
        
        # Обычный пользователь получит 403
        assert response.status_code == 403


class TestAdminAPI:
    """Тесты для API Admin"""
    
    @pytest.mark.asyncio
    async def test_update_balance_requires_admin(self, frontend_client):
        """Проверяем что API требует прав admin"""
        response = await frontend_client.post(
            "/frontend/admin/api/companies/test_company/balance",
            json={"amount": 1000}
        )
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_update_tariff_requires_admin(self, frontend_client):
        """Проверяем что API требует прав admin"""
        response = await frontend_client.post(
            "/frontend/admin/api/companies/test_company/tariff",
            json={"tariff": "basic"}
        )
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_reset_billing_requires_admin(self, frontend_client):
        """Проверяем что API требует прав admin"""
        response = await frontend_client.post(
            "/frontend/admin/api/companies/test_company/reset-billing"
        )
        
        assert response.status_code == 403

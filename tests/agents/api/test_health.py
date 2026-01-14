"""
Тесты базовых endpoints.

Реальный сервис, без моков.
"""

import pytest


class TestHealthEndpoint:
    """Тесты health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """Health endpoint возвращает ok."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "agents"


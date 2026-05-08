"""Маршрут каталога речи не должен отдаваться SPA fallback как 404."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_voice_providers_catalog_reaches_fastapi_not_auth_404(
    frontend_client: AsyncClient,
) -> None:
    """Без cookie: 401 из хендлера; 404 — регрессия AuthMiddleware (нет правила для пути)."""
    response = await frontend_client.get("/frontend/api/voice-providers/catalog")
    assert response.status_code == 401, response.text

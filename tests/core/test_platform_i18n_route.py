"""Публичный маршрут переводов доступен на всех сервисах (не только frontend)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_sync_app_exposes_i18n_ru() -> None:
    from apps.sync.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/i18n/ru")

    assert response.status_code == 200
    payload = response.json()
    assert "platform" in payload
    assert "landing" in payload
    assert payload["platform"]["menu"]["logout"]
    assert "billing" in payload
    detail = payload["billing"]["notifications"]["balance_blocked_api_detail"]
    assert isinstance(detail, str) and len(detail) > 0


@pytest.mark.asyncio
async def test_sync_app_rejects_unknown_locale() -> None:
    from apps.sync.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/i18n/de")

    assert response.status_code == 400

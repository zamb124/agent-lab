"""Публичная страница поддержки /support (App Store Support URL)."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient


@pytest.mark.asyncio
async def test_support_page_available_without_auth(
    frontend_client: AsyncClient,
) -> None:
    """GET /support отдаёт SPA (контент страницы support — в клиенте, строки из i18n)."""
    response = await frontend_client.get("/support")
    assert response.status_code == 200
    text = response.text
    assert "<!DOCTYPE html>" in text
    assert "<frontend-app" in text


@pytest.mark.asyncio
async def test_support_page_prefixed_frontend_path(
    frontend_client: AsyncClient,
) -> None:
    """Тот же контент по /frontend/support для gateway."""
    response = await frontend_client.get("/frontend/support")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text


@pytest.mark.asyncio
async def test_support_in_sitemap(frontend_client: AsyncClient) -> None:
    """Sitemap-index ведёт на маркетинг-карту, где есть канонический /support."""
    index_response = await frontend_client.get("/sitemap.xml")
    assert index_response.status_code == 200
    assert "sitemapindex" in index_response.text
    assert "sitemap-marketing.xml" in index_response.text

    response = await frontend_client.get("/sitemap-marketing.xml")
    assert response.status_code == 200
    assert "/support</loc>" in response.text

"""
Тесты для публичных страниц (landing, privacy, terms).

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def public_client(frontend_app):
    """Клиент для публичных страниц (без авторизации)"""
    transport = ASGITransport(app=frontend_app)
    async with AsyncClient(transport=transport, base_url="http://localhost:8002") as client:
        yield client


class TestPublicPages:
    """Тесты для публичных страниц"""
    
    @pytest.mark.asyncio
    async def test_landing_page(self, public_client):
        """Проверяем landing page"""
        response = await public_client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_privacy_page(self, public_client):
        """Проверяем страницу политики конфиденциальности"""
        response = await public_client.get("/privacy")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_privacy_page_with_lang(self, public_client):
        """Проверяем политику конфиденциальности на разных языках"""
        response_ru = await public_client.get("/privacy?lang=ru")
        response_en = await public_client.get("/privacy?lang=en")
        
        assert response_ru.status_code == 200
        assert response_en.status_code == 200
    
    @pytest.mark.asyncio
    async def test_terms_page(self, public_client):
        """Проверяем страницу пользовательского соглашения"""
        response = await public_client.get("/terms")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_terms_page_with_lang(self, public_client):
        """Проверяем соглашение на разных языках"""
        response_ru = await public_client.get("/terms?lang=ru")
        response_en = await public_client.get("/terms?lang=en")
        
        assert response_ru.status_code == 200
        assert response_en.status_code == 200

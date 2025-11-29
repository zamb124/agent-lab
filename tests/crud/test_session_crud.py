"""
Тесты для CRUD роутера SessionRepository.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from apps.agents.main import create_app
from tests.conftest import test_context, save_test_company


@pytest_asyncio.fixture
async def app(migrated_db, test_context, save_test_company):
    """FastAPI приложение для тестов"""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Асинхронный тестовый клиент"""
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_session_data():
    """Тестовые данные session"""
    return {
        "session_id": "test_session_123",
        "flow_id": "test_flow",
        "user_id": "test_user",
        "platform": "api",
        "status": "active"
    }


@pytest.mark.asyncio
async def test_list_sessions_empty(client):
    """Тест получения списка sessions"""
    response = await client.get("/agents/api/v1/session")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_session(client, test_session_data):
    """Тест создания session"""
    response = await client.post("/agents/api/v1/session", json=test_session_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["session_id"] == test_session_data["session_id"]


@pytest.mark.asyncio
async def test_get_session(client, test_session_data):
    """Тест получения session по ID"""
    await client.post("/agents/api/v1/session", json=test_session_data)
    
    response = await client.get(f"/agents/api/v1/session/{test_session_data['session_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["session_id"] == test_session_data["session_id"]


@pytest.mark.asyncio
async def test_delete_session(client, test_session_data):
    """Тест удаления session"""
    await client.post("/agents/api/v1/session", json=test_session_data)
    
    response = await client.delete(f"/agents/api/v1/session/{test_session_data['session_id']}")
    assert response.status_code == 200
    
    get_response = await client.get(f"/agents/api/v1/session/{test_session_data['session_id']}")
    assert get_response.status_code == 404


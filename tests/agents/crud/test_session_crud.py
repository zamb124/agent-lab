"""
Тесты для CRUD роутера SessionRepository.
"""

import pytest


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
async def test_list_sessions_empty(agents_client):
    """Тест получения списка sessions"""
    response = await agents_client.get("/agents/api/v1/session")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_session(agents_client, test_session_data):
    """Тест создания session"""
    response = await agents_client.post("/agents/api/v1/session", json=test_session_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["session_id"] == test_session_data["session_id"]


@pytest.mark.asyncio
async def test_get_session(agents_client, test_session_data):
    """Тест получения session по ID"""
    await agents_client.post("/agents/api/v1/session", json=test_session_data)
    
    response = await agents_client.get(f"/agents/api/v1/session/{test_session_data['session_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["session_id"] == test_session_data["session_id"]


@pytest.mark.asyncio
async def test_delete_session(agents_client, test_session_data):
    """Тест удаления session"""
    await agents_client.post("/agents/api/v1/session", json=test_session_data)
    
    response = await agents_client.delete(f"/agents/api/v1/session/{test_session_data['session_id']}")
    assert response.status_code == 200
    
    get_response = await agents_client.get(f"/agents/api/v1/session/{test_session_data['session_id']}")
    assert get_response.status_code == 404

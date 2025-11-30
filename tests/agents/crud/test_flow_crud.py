"""
Тесты для CRUD роутера FlowRepository.
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
def test_flow_data():
    """Тестовые данные flow"""
    return {
        "flow_id": "test_flow_123",
        "name": "Test Flow",
        "description": "Test flow for CRUD tests",
        "entry_point_agent": "test_agent",
        "source": "test"
    }


@pytest.mark.asyncio
async def test_list_flows_empty(client):
    """Тест получения списка flows"""
    response = await client.get("/agents/api/v1/flow")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_flow(client, test_flow_data):
    """Тест создания flow"""
    response = await client.post("/agents/api/v1/flow", json=test_flow_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["flow_id"] == test_flow_data["flow_id"]
    assert data["name"] == test_flow_data["name"]


@pytest.mark.asyncio
async def test_get_flow(client, test_flow_data):
    """Тест получения flow по ID"""
    await client.post("/agents/api/v1/flow", json=test_flow_data)
    
    response = await client.get(f"/agents/api/v1/flow/{test_flow_data['flow_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["flow_id"] == test_flow_data["flow_id"]


@pytest.mark.asyncio
async def test_get_flow_not_found(client):
    """Тест получения несуществующего flow"""
    response = await client.get("/agents/api/v1/flow/non_existent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_flow(client, test_flow_data):
    """Тест обновления flow"""
    await client.post("/agents/api/v1/flow", json=test_flow_data)
    
    updated_data = test_flow_data.copy()
    updated_data["name"] = "Updated Flow Name"
    
    response = await client.post("/agents/api/v1/flow", json=updated_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "Updated Flow Name"


@pytest.mark.asyncio
async def test_delete_flow(client, test_flow_data):
    """Тест удаления flow"""
    await client.post("/agents/api/v1/flow", json=test_flow_data)
    
    response = await client.delete(f"/agents/api/v1/flow/{test_flow_data['flow_id']}")
    assert response.status_code == 200
    
    get_response = await client.get(f"/agents/api/v1/flow/{test_flow_data['flow_id']}")
    assert get_response.status_code == 404


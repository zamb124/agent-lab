"""
Тесты для CRUD роутера FlowRepository.
"""

import pytest


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
async def test_list_flows_empty(agents_client):
    """Тест получения списка flows"""
    response = await agents_client.get("/agents/api/v1/flow")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_flow(agents_client, test_flow_data):
    """Тест создания flow"""
    response = await agents_client.post("/agents/api/v1/flow", json=test_flow_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["flow_id"] == test_flow_data["flow_id"]
    assert data["name"] == test_flow_data["name"]


@pytest.mark.asyncio
async def test_get_flow(agents_client, test_flow_data):
    """Тест получения flow по ID"""
    await agents_client.post("/agents/api/v1/flow", json=test_flow_data)
    
    response = await agents_client.get(f"/agents/api/v1/flow/{test_flow_data['flow_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["flow_id"] == test_flow_data["flow_id"]


@pytest.mark.asyncio
async def test_get_flow_not_found(agents_client):
    """Тест получения несуществующего flow"""
    response = await agents_client.get("/agents/api/v1/flow/non_existent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_flow(agents_client, test_flow_data):
    """Тест обновления flow"""
    await agents_client.post("/agents/api/v1/flow", json=test_flow_data)
    
    updated_data = test_flow_data.copy()
    updated_data["name"] = "Updated Flow Name"
    
    response = await agents_client.post("/agents/api/v1/flow", json=updated_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "Updated Flow Name"


@pytest.mark.asyncio
async def test_delete_flow(agents_client, test_flow_data):
    """Тест удаления flow"""
    await agents_client.post("/agents/api/v1/flow", json=test_flow_data)
    
    response = await agents_client.delete(f"/agents/api/v1/flow/{test_flow_data['flow_id']}")
    assert response.status_code == 200
    
    get_response = await agents_client.get(f"/agents/api/v1/flow/{test_flow_data['flow_id']}")
    assert get_response.status_code == 404

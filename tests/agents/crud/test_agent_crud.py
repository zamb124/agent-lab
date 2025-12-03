"""
Тесты для CRUD роутера AgentRepository.
"""

import pytest


@pytest.fixture
def test_agent_data():
    """Тестовые данные агента"""
    return {
        "agent_id": "test_agent_123",
        "name": "Test Agent",
        "description": "Test agent for CRUD tests",
        "type": "react",
        "code_mode": "code_reference",
        "function_class": None,
        "prompt": "You are a test agent",
        "tools": [],
        "llm_config": {
            "model": "mock-gpt-4",
            "temperature": 0.3,
            "context_window": 10000
        },
        "source": "test"
    }


@pytest.mark.asyncio
async def test_list_agents_empty(agents_client):
    """Тест получения списка агентов"""
    response = await agents_client.get("/agents/api/v1/agent")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_agent(agents_client, test_agent_data):
    """Тест создания агента"""
    response = await agents_client.post("/agents/api/v1/agent", json=test_agent_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["agent_id"] == test_agent_data["agent_id"]
    assert data["name"] == test_agent_data["name"]


@pytest.mark.asyncio
async def test_get_agent(agents_client, test_agent_data):
    """Тест получения агента по ID"""
    create_response = await agents_client.post("/agents/api/v1/agent", json=test_agent_data)
    assert create_response.status_code == 200
    
    response = await agents_client.get(f"/agents/api/v1/agent/{test_agent_data['agent_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["agent_id"] == test_agent_data["agent_id"]
    assert data["name"] == test_agent_data["name"]


@pytest.mark.asyncio
async def test_get_agent_not_found(agents_client):
    """Тест получения несуществующего агента"""
    response = await agents_client.get("/agents/api/v1/agent/non_existent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_agent(agents_client, test_agent_data):
    """Тест обновления агента"""
    await agents_client.post("/agents/api/v1/agent", json=test_agent_data)
    
    updated_data = test_agent_data.copy()
    updated_data["name"] = "Updated Agent Name"
    
    response = await agents_client.post("/agents/api/v1/agent", json=updated_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "Updated Agent Name"


@pytest.mark.asyncio
async def test_delete_agent(agents_client, test_agent_data):
    """Тест удаления агента"""
    await agents_client.post("/agents/api/v1/agent", json=test_agent_data)
    
    response = await agents_client.delete(f"/agents/api/v1/agent/{test_agent_data['agent_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert data["entity_id"] == test_agent_data["agent_id"]
    
    get_response = await agents_client.get(f"/agents/api/v1/agent/{test_agent_data['agent_id']}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_agent_not_found(agents_client):
    """Тест удаления несуществующего агента"""
    response = await agents_client.delete("/agents/api/v1/agent/non_existent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_agents_with_pagination(agents_client, test_agent_data):
    """Тест получения списка агентов с пагинацией"""
    for i in range(5):
        agent_data = test_agent_data.copy()
        agent_data["agent_id"] = f"test_agent_{i}"
        agent_data["name"] = f"Test Agent {i}"
        await agents_client.post("/agents/api/v1/agent", json=agent_data)
    
    response = await agents_client.get("/agents/api/v1/agent?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 3
    
    response = await agents_client.get("/agents/api/v1/agent?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 2


@pytest.mark.asyncio
async def test_get_many_agents(agents_client, test_agent_data):
    """Тест получения нескольких агентов по ID"""
    agent_ids = []
    for i in range(3):
        agent_data = test_agent_data.copy()
        agent_data["agent_id"] = f"test_agent_{i}"
        agent_data["name"] = f"Test Agent {i}"
        await agents_client.post("/agents/api/v1/agent", json=agent_data)
        agent_ids.append(f"test_agent_{i}")
    
    response = await agents_client.post("/agents/api/v1/agent/many", json=agent_ids)
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 3
    for agent_id in agent_ids:
        assert agent_id in data
        assert data[agent_id]["agent_id"] == agent_id


@pytest.mark.asyncio
async def test_get_many_agents_empty(agents_client):
    """Тест получения пустого списка агентов"""
    response = await agents_client.post("/agents/api/v1/agent/many", json=[])
    assert response.status_code == 200
    assert response.json() == {}


@pytest.mark.asyncio
async def test_create_agent_invalid_data(agents_client):
    """Тест создания агента с невалидными данными"""
    invalid_data = {"invalid": "data"}
    response = await agents_client.post("/agents/api/v1/agent", json=invalid_data)
    assert response.status_code == 400

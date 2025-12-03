"""
Тесты для CRUD роутера ToolRepository.
"""

import pytest


@pytest.fixture
def test_tool_data():
    """Тестовые данные tool"""
    return {
        "tool_id": "test_tool_123",
        "code_mode": "inline_code",
        "inline_code": "def test_tool(): return 'test'",
        "description": "Test tool for CRUD tests"
    }


@pytest.mark.asyncio
async def test_list_tools_empty(agents_client):
    """Тест получения списка tools"""
    response = await agents_client.get("/agents/api/v1/tool")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_tool(agents_client, test_tool_data):
    """Тест создания tool"""
    response = await agents_client.post("/agents/api/v1/tool", json=test_tool_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["tool_id"] == test_tool_data["tool_id"]


@pytest.mark.asyncio
async def test_get_tool(agents_client, test_tool_data):
    """Тест получения tool по ID"""
    await agents_client.post("/agents/api/v1/tool", json=test_tool_data)
    
    response = await agents_client.get(f"/agents/api/v1/tool/{test_tool_data['tool_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["tool_id"] == test_tool_data["tool_id"]


@pytest.mark.asyncio
async def test_delete_tool(agents_client, test_tool_data):
    """Тест удаления tool"""
    await agents_client.post("/agents/api/v1/tool", json=test_tool_data)
    
    response = await agents_client.delete(f"/agents/api/v1/tool/{test_tool_data['tool_id']}")
    assert response.status_code == 200
    
    get_response = await agents_client.get(f"/agents/api/v1/tool/{test_tool_data['tool_id']}")
    assert get_response.status_code == 404

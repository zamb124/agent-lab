"""
Тесты для CRUD роутера MCPServerRepository.
"""

import pytest


@pytest.fixture
def test_mcp_server_data():
    """Тестовые данные MCP сервера"""
    return {
        "server_id": "test_mcp_server_123",
        "company_id": "test_company",
        "name": "Test MCP Server",
        "description": "Test MCP server for CRUD tests",
        "url": "https://example.com/mcp",
        "transport_type": "http",
        "headers": {},
        "is_active": True,
        "auto_sync_tools": False
    }


@pytest.mark.asyncio
async def test_list_mcp_servers_empty(agents_client):
    """Тест получения списка MCP серверов"""
    response = await agents_client.get("/agents/api/v1/mcp_server")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_mcp_server(agents_client, test_mcp_server_data):
    """Тест создания MCP сервера"""
    response = await agents_client.post("/agents/api/v1/mcp_server", json=test_mcp_server_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["server_id"] == test_mcp_server_data["server_id"]


@pytest.mark.asyncio
async def test_get_mcp_server(agents_client, test_mcp_server_data):
    """Тест получения MCP сервера по ID"""
    await agents_client.post("/agents/api/v1/mcp_server", json=test_mcp_server_data)
    
    response = await agents_client.get(f"/agents/api/v1/mcp_server/{test_mcp_server_data['server_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["server_id"] == test_mcp_server_data["server_id"]


@pytest.mark.asyncio
async def test_delete_mcp_server(agents_client, test_mcp_server_data):
    """Тест удаления MCP сервера"""
    await agents_client.post("/agents/api/v1/mcp_server", json=test_mcp_server_data)
    
    response = await agents_client.delete(f"/agents/api/v1/mcp_server/{test_mcp_server_data['server_id']}")
    assert response.status_code == 200
    
    get_response = await agents_client.get(f"/agents/api/v1/mcp_server/{test_mcp_server_data['server_id']}")
    assert get_response.status_code == 404

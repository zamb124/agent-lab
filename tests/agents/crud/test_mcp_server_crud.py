"""
Тесты для CRUD роутера MCPServerRepository.
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
async def test_list_mcp_servers_empty(client):
    """Тест получения списка MCP серверов"""
    response = await client.get("/agents/api/v1/mcp_server")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_mcp_server(client, test_mcp_server_data):
    """Тест создания MCP сервера"""
    response = await client.post("/agents/api/v1/mcp_server", json=test_mcp_server_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["server_id"] == test_mcp_server_data["server_id"]


@pytest.mark.asyncio
async def test_get_mcp_server(client, test_mcp_server_data):
    """Тест получения MCP сервера по ID"""
    await client.post("/agents/api/v1/mcp_server", json=test_mcp_server_data)
    
    response = await client.get(f"/agents/api/v1/mcp_server/{test_mcp_server_data['server_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["server_id"] == test_mcp_server_data["server_id"]


@pytest.mark.asyncio
async def test_delete_mcp_server(client, test_mcp_server_data):
    """Тест удаления MCP сервера"""
    await client.post("/agents/api/v1/mcp_server", json=test_mcp_server_data)
    
    response = await client.delete(f"/agents/api/v1/mcp_server/{test_mcp_server_data['server_id']}")
    assert response.status_code == 200
    
    get_response = await client.get(f"/agents/api/v1/mcp_server/{test_mcp_server_data['server_id']}")
    assert get_response.status_code == 404


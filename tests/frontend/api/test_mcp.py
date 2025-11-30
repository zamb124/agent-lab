"""
Тесты для API MCP серверов.

Используется реальная БД без моков.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import MCPServerConfig


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_mcp_server(frontend_mcp_repo, frontend_client) -> MCPServerConfig:
    """Тестовый MCP сервер"""
    server_id = make_unique_id("mcp_server")
    server = MCPServerConfig(
        server_id=server_id,
        name="Test MCP Server",
        url="http://localhost:8003/mcp-api",
        description="A test server for MCP",
        transport_type="http",
        headers={},
        timeout=30,
        is_active=True,
        auto_sync_tools=True,
        cached_tools=[]
    )
    await frontend_mcp_repo.set(server)
    yield server
    await frontend_mcp_repo.delete(server_id)


class TestMCPServerListAPI:
    """Тесты для GET /frontend/api/mcp/servers endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_servers(self, frontend_client, test_mcp_server):
        """Проверяем получение списка MCP серверов"""
        response = await frontend_client.get("/frontend/api/mcp/servers")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMCPServerDetailAPI:
    """Тесты для GET /frontend/api/mcp/servers/{server_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_server(self, frontend_client, test_mcp_server):
        """Проверяем получение MCP сервера по ID"""
        response = await frontend_client.get(f"/frontend/api/mcp/servers/{test_mcp_server.server_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["server_id"] == test_mcp_server.server_id
    
    @pytest.mark.asyncio
    async def test_get_server_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего сервера"""
        response = await frontend_client.get("/frontend/api/mcp/servers/nonexistent_server")
        
        assert response.status_code == 404


class TestMCPServerCreateAPI:
    """Тесты для POST /frontend/api/mcp/servers endpoint"""
    
    @pytest.mark.asyncio
    async def test_create_mcp_server(self, frontend_client, frontend_mcp_repo):
        """Проверяем создание нового MCP сервера"""
        server_name = make_unique_id("new_mcp_server")
        server_data = {
            "name": server_name,
            "url": "http://localhost:8004/mcp-api",
            "description": "New test server"
        }
        
        response = await frontend_client.post("/frontend/api/mcp/servers", json=server_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "server_id" in data
        
        # Очистка
        await frontend_mcp_repo.delete(data["server_id"])


class TestMCPServerUpdateAPI:
    """Тесты для PUT /frontend/api/mcp/servers/{server_id} endpoint"""

    @pytest.mark.asyncio
    async def test_update_mcp_server(self, frontend_client, test_mcp_server):
        """Проверяем обновление MCP сервера"""
        response = await frontend_client.put(
            f"/frontend/api/mcp/servers/{test_mcp_server.server_id}",
            json={"name": "Updated MCP Server Name"}
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_mcp_server_not_found(self, frontend_client):
        """Проверяем 404 при обновлении несуществующего сервера"""
        response = await frontend_client.put(
            "/frontend/api/mcp/servers/nonexistent_server",
            json={"name": "Nonexistent"}
        )
        assert response.status_code == 404


class TestMCPServerDeleteAPI:
    """Тесты для DELETE /frontend/api/mcp/servers/{server_id} endpoint"""

    @pytest.mark.asyncio
    async def test_delete_mcp_server(self, frontend_client, test_mcp_server, frontend_mcp_repo):
        """Проверяем удаление MCP сервера"""
        response = await frontend_client.delete(f"/frontend/api/mcp/servers/{test_mcp_server.server_id}")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_mcp_server_not_found(self, frontend_client):
        """Проверяем 404 при удалении несуществующего сервера"""
        response = await frontend_client.delete("/frontend/api/mcp/servers/nonexistent_server")
        assert response.status_code == 404

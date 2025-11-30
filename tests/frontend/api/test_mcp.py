"""
Тесты для API MCP серверов.

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio

from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType


@pytest_asyncio.fixture
async def test_mcp_server(mcp_repo, test_company, unique_id, test_context) -> MCPServerConfig:
    """Тестовый MCP сервер"""
    server_id = unique_id("mcp_server")
    server = MCPServerConfig(
        server_id=server_id,
        company_id=test_company.company_id,
        name="Test MCP Server",
        description="Server for API testing",
        url="https://test-mcp.example.com/api",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": "Bearer test-token"},
        is_active=True,
        auto_sync_tools=False
    )
    await mcp_repo.set(server)
    yield server
    await mcp_repo.delete(server_id)


class TestMCPServersListAPI:
    """Тесты для GET /frontend/api/mcp/servers endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_mcp_servers(self, frontend_client, test_mcp_server):
        """Проверяем получение списка MCP серверов"""
        response = await frontend_client.get("/frontend/api/mcp/servers")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        server_ids = [s["server_id"] for s in data]
        assert test_mcp_server.server_id in server_ids
    
    @pytest.mark.asyncio
    async def test_list_mcp_servers_empty(self, frontend_client):
        """Проверяем пустой список"""
        response = await frontend_client.get("/frontend/api/mcp/servers")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMCPServerDetailAPI:
    """Тесты для GET /frontend/api/mcp/servers/{server_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_mcp_server(self, frontend_client, test_mcp_server):
        """Проверяем получение MCP сервера по ID"""
        response = await frontend_client.get(
            f"/frontend/api/mcp/servers/{test_mcp_server.server_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["server_id"] == test_mcp_server.server_id
        assert data["name"] == "Test MCP Server"
        assert data["is_active"] is True
    
    @pytest.mark.asyncio
    async def test_get_mcp_server_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего сервера"""
        response = await frontend_client.get("/frontend/api/mcp/servers/nonexistent")
        
        assert response.status_code == 404


class TestMCPServerCreateAPI:
    """Тесты для POST /frontend/api/mcp/servers endpoint"""
    
    @pytest.mark.asyncio
    async def test_create_mcp_server(self, frontend_client, mcp_repo, test_company, unique_id):
        """Проверяем создание MCP сервера"""
        server_id = unique_id("new_mcp")
        
        server_data = {
            "server_id": server_id,
            "company_id": test_company.company_id,
            "name": "New MCP Server",
            "description": "Created via API",
            "url": "https://new-mcp.example.com/api",
            "transport_type": "http",
            "headers": {},
            "is_active": True,
            "auto_sync_tools": False
        }
        
        response = await frontend_client.post("/frontend/api/mcp/servers", json=server_data)
        
        assert response.status_code == 200
        
        created_server = await mcp_repo.get(server_id)
        assert created_server is not None
        assert created_server.name == "New MCP Server"
        
        await mcp_repo.delete(server_id)
    
    @pytest.mark.asyncio
    async def test_create_mcp_server_missing_url(self, frontend_client, test_company, unique_id):
        """Проверяем ошибку при отсутствии URL"""
        server_data = {
            "server_id": unique_id("no_url"),
            "company_id": test_company.company_id,
            "name": "No URL Server"
        }
        
        response = await frontend_client.post("/frontend/api/mcp/servers", json=server_data)
        
        assert response.status_code in [400, 422]


class TestMCPServerUpdateAPI:
    """Тесты для PUT /frontend/api/mcp/servers/{server_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_update_mcp_server(self, frontend_client, test_mcp_server, mcp_repo):
        """Проверяем обновление MCP сервера"""
        update_data = {
            "name": "Updated Server Name",
            "is_active": False
        }
        
        response = await frontend_client.put(
            f"/frontend/api/mcp/servers/{test_mcp_server.server_id}",
            json=update_data
        )
        
        assert response.status_code == 200
        
        updated_server = await mcp_repo.get(test_mcp_server.server_id)
        assert updated_server.name == "Updated Server Name"
        assert updated_server.is_active is False
    
    @pytest.mark.asyncio
    async def test_update_mcp_server_not_found(self, frontend_client):
        """Проверяем 404 при обновлении несуществующего сервера"""
        response = await frontend_client.put(
            "/frontend/api/mcp/servers/nonexistent",
            json={"name": "Updated"}
        )
        
        assert response.status_code == 404


class TestMCPServerDeleteAPI:
    """Тесты для DELETE /frontend/api/mcp/servers/{server_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_delete_mcp_server(self, frontend_client, mcp_repo, test_company, unique_id):
        """Проверяем удаление MCP сервера"""
        server_id = unique_id("del_mcp")
        server = MCPServerConfig(
            server_id=server_id,
            company_id=test_company.company_id,
            name="To Delete",
            url="https://delete.example.com",
            transport_type=MCPTransportType.HTTP
        )
        await mcp_repo.set(server)
        
        response = await frontend_client.delete(f"/frontend/api/mcp/servers/{server_id}")
        
        assert response.status_code == 200
        
        deleted = await mcp_repo.get(server_id)
        assert deleted is None
    
    @pytest.mark.asyncio
    async def test_delete_mcp_server_not_found(self, frontend_client):
        """Проверяем 404 при удалении несуществующего сервера"""
        response = await frontend_client.delete("/frontend/api/mcp/servers/nonexistent")
        
        assert response.status_code == 404


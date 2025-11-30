"""
Тесты для модуля MCP (страницы управления MCP серверами).

Используется реальная БД без моков.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models.mcp_models import MCPServerConfig


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_mcp_server_for_page(frontend_mcp_repo, frontend_client) -> MCPServerConfig:
    """Тестовый MCP сервер для страниц"""
    server_id = make_unique_id("mcp_page_server")
    server = MCPServerConfig(
        server_id=server_id,
        name="MCP Page Test Server",
        url="http://localhost:8080",
        description="Test server for page testing",
        transport_type="http",
        headers={},
        timeout=30,
        is_active=True,
        auto_sync_tools=False,
        cached_tools=[]
    )
    await frontend_mcp_repo.set(server)
    yield server
    await frontend_mcp_repo.delete(server_id)


class TestMCPPageRoutes:
    """Тесты для страниц MCP"""
    
    @pytest.mark.asyncio
    async def test_mcp_main_page(self, frontend_client):
        """Проверяем главную страницу MCP"""
        response = await frontend_client.get("/frontend/mcp/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_mcp_servers_list(self, frontend_client, test_mcp_server_for_page):
        """Проверяем список MCP серверов"""
        response = await frontend_client.get("/frontend/mcp/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_mcp_server_details_existing(self, frontend_client, test_mcp_server_for_page):
        """Проверяем детали существующего сервера"""
        response = await frontend_client.get(
            f"/frontend/mcp/{test_mcp_server_for_page.server_id}/details"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_mcp_server_details_new(self, frontend_client):
        """Проверяем форму создания нового сервера"""
        response = await frontend_client.get("/frontend/mcp/new/details")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_mcp_server_details_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего сервера"""
        response = await frontend_client.get("/frontend/mcp/nonexistent_server/details")
        
        assert response.status_code == 404

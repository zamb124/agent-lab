"""
Юнит тесты для синхронизации MCP тулов.
"""

import pytest
from unittest.mock import AsyncMock, patch

from apps.agents.services.mcp_sync import sync_mcp_server_tools
from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
from apps.agents.models.core_models import CodeMode


@pytest.fixture
def sample_server_config():
    """Фикстура с MCP сервером"""
    return MCPServerConfig(
        server_id="test_server",
        company_id="test_company",
        name="Test MCP",
        url="https://mcp.example.com/mcp",
        transport_type=MCPTransportType.HTTP,
        is_active=True
    )


@pytest.mark.asyncio
async def test_sync_mcp_server_tools(sample_server_config, mcp_repo, tool_repo):
    """Тест синхронизации тулов MCP сервера"""
    await mcp_repo.set(sample_server_config)
    
    mock_tools_data = [
        {
            "name": "search_docs",
            "description": "Search documentation",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_file",
            "description": "Get file content",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    ]
    
    mock_client = AsyncMock()
    mock_client.list_tools = AsyncMock(return_value=mock_tools_data)
    
    with patch('apps.agents.services.mcp_sync.get_mcp_client', return_value=mock_client):
        tools = await sync_mcp_server_tools("test_server", "test_company")
        
        assert len(tools) == 2
        
        assert tools[0].tool_id == "mcp:test_server:search_docs"
        assert tools[0].title == "search_docs"
        assert tools[0].description == "Search documentation"
        assert tools[0].code_mode == CodeMode.MCP_TOOL
        assert tools[0].params["server_id"] == "test_server"
        assert tools[0].params["company_id"] == "test_company"
        assert tools[0].params["tool_name"] == "search_docs"
        assert "input_schema" in tools[0].params
        
        assert tools[1].tool_id == "mcp:test_server:get_file"
        assert tools[1].title == "get_file"
        
        saved_tool = await tool_repo.get("mcp:test_server:search_docs")
        assert saved_tool is not None
        assert saved_tool.code_mode == CodeMode.MCP_TOOL
        
        updated_server = await mcp_repo.get("test_server")
        assert len(updated_server.cached_tools) == 2
        assert "mcp:test_server:search_docs" in updated_server.cached_tools
        assert updated_server.last_sync_at is not None


@pytest.mark.asyncio
async def test_sync_inactive_server_fails(sample_server_config, mcp_repo):
    """Тест что синхронизация неактивного сервера падает"""
    sample_server_config.is_active = False
    
    await mcp_repo.set(sample_server_config)
    
    with pytest.raises(ValueError, match="неактивен"):
        await sync_mcp_server_tools("test_server", "test_company")


@pytest.mark.asyncio
async def test_sync_nonexistent_server_fails(mcp_repo):
    """Тест что синхронизация несуществующего сервера падает"""
    with pytest.raises(ValueError, match="не найден"):
        await sync_mcp_server_tools("nonexistent_server", "test_company")


@pytest.mark.asyncio
async def test_sync_skips_tools_without_name(sample_server_config, mcp_repo):
    """Тест что тулы без имени пропускаются"""
    await mcp_repo.set(sample_server_config)
    
    mock_tools_data = [
        {
            "name": "valid_tool",
            "description": "Valid tool"
        },
        {
            "description": "Invalid tool"
        },
        {
            "name": "",
            "description": "Empty name"
        }
    ]
    
    mock_client = AsyncMock()
    mock_client.list_tools = AsyncMock(return_value=mock_tools_data)
    
    with patch('apps.agents.services.mcp_sync.get_mcp_client', return_value=mock_client):
        tools = await sync_mcp_server_tools("test_server", "test_company")
        
        assert len(tools) == 1
        assert tools[0].tool_id == "mcp:test_server:valid_tool"

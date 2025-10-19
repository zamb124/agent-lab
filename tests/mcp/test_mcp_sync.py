"""
Юнит тесты для синхронизации MCP тулов.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.mcp_sync import sync_mcp_server_tools
from app.models.mcp_models import MCPServerConfig, MCPTransportType
from app.models import ToolReference
from app.models.core_models import CodeMode
from app.db.repositories.mcp_repository import MCPServerRepository
from app.db.repositories.tool_repository import ToolRepository
from app.db.repositories.storage import Storage


@pytest.fixture
async def storage():
    """Фикстура для Storage"""
    storage = Storage()
    yield storage
    # Очистка после тестов
    keys = await storage.list_by_prefix("mcp_server:", limit=1000)
    for key in keys:
        await storage.delete(key)
    keys = await storage.list_by_prefix("tool:", limit=1000)
    for key in keys:
        await storage.delete(key)


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
async def test_sync_mcp_server_tools(storage, sample_server_config):
    """Тест синхронизации тулов MCP сервера"""
    # Подготовка
    mcp_repo = MCPServerRepository(storage)
    await mcp_repo.set(sample_server_config)
    
    # Мокаем MCP клиент
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
    
    with patch('app.core.mcp_sync.get_mcp_client', return_value=mock_client):
        # Выполняем синхронизацию
        tools = await sync_mcp_server_tools("test_server", "test_company")
        
        # Проверки
        assert len(tools) == 2
        
        # Проверяем первый тул
        assert tools[0].tool_id == "mcp:test_server:search_docs"
        assert tools[0].title == "search_docs"
        assert tools[0].description == "Search documentation"
        assert tools[0].code_mode == CodeMode.MCP_TOOL
        assert tools[0].params["server_id"] == "test_server"
        assert tools[0].params["company_id"] == "test_company"
        assert tools[0].params["tool_name"] == "search_docs"
        assert "inputSchema" in tools[0].params
        
        # Проверяем второй тул
        assert tools[1].tool_id == "mcp:test_server:get_file"
        assert tools[1].title == "get_file"
        
        # Проверяем что тулы сохранены в БД
        tool_repo = ToolRepository(storage)
        saved_tool = await tool_repo.get("mcp:test_server:search_docs")
        assert saved_tool is not None
        assert saved_tool.code_mode == CodeMode.MCP_TOOL
        
        # Проверяем что кэш обновлен
        updated_server = await mcp_repo.get("test_server", "test_company")
        assert len(updated_server.cached_tools) == 2
        assert "mcp:test_server:search_docs" in updated_server.cached_tools
        assert updated_server.last_sync_at is not None


@pytest.mark.asyncio
async def test_sync_inactive_server_fails(storage, sample_server_config):
    """Тест что синхронизация неактивного сервера падает"""
    # Делаем сервер неактивным
    sample_server_config.is_active = False
    
    mcp_repo = MCPServerRepository(storage)
    await mcp_repo.set(sample_server_config)
    
    # Ожидаем ошибку
    with pytest.raises(ValueError, match="неактивен"):
        await sync_mcp_server_tools("test_server", "test_company")


@pytest.mark.asyncio
async def test_sync_nonexistent_server_fails(storage):
    """Тест что синхронизация несуществующего сервера падает"""
    with pytest.raises(ValueError, match="не найден"):
        await sync_mcp_server_tools("nonexistent_server", "test_company")


@pytest.mark.asyncio
async def test_sync_skips_tools_without_name(storage, sample_server_config):
    """Тест что тулы без имени пропускаются"""
    mcp_repo = MCPServerRepository(storage)
    await mcp_repo.set(sample_server_config)
    
    # Мокаем данные с тулом без имени
    mock_tools_data = [
        {
            "name": "valid_tool",
            "description": "Valid tool"
        },
        {
            # Нет имени
            "description": "Invalid tool"
        },
        {
            "name": "",  # Пустое имя
            "description": "Empty name"
        }
    ]
    
    mock_client = AsyncMock()
    mock_client.list_tools = AsyncMock(return_value=mock_tools_data)
    
    with patch('app.core.mcp_sync.get_mcp_client', return_value=mock_client):
        tools = await sync_mcp_server_tools("test_server", "test_company")
        
        # Только 1 валидный тул
        assert len(tools) == 1
        assert tools[0].tool_id == "mcp:test_server:valid_tool"


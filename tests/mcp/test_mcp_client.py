"""
Юнит тесты для MCP HTTP клиента.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.core.mcp_client import MCPHttpClient, format_mcp_result
from app.models.mcp_models import MCPTransportType


@pytest.fixture
def http_client():
    """Фикстура для HTTP MCP клиента"""
    return MCPHttpClient(
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer test_token"},
        timeout=30,
        transport_type=MCPTransportType.HTTP
    )


@pytest.fixture
def sse_client():
    """Фикстура для SSE MCP клиента"""
    return MCPHttpClient(
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer test_token"},
        timeout=30,
        transport_type=MCPTransportType.SSE
    )


@pytest.mark.asyncio
async def test_list_tools_http(http_client):
    """Тест получения списка тулов через HTTP"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "tools": [
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
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    
    with patch.object(http_client, '_get_client', return_value=AsyncMock()) as mock_get_client:
        mock_client = await mock_get_client()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        tools = await http_client.list_tools()
        
        assert len(tools) == 1
        assert tools[0]["name"] == "search_docs"
        assert tools[0]["description"] == "Search documentation"
        mock_client.post.assert_called_once_with("https://mcp.example.com/mcp/list_tools", json={})


@pytest.mark.asyncio
async def test_call_tool_http_success(http_client):
    """Тест успешного вызова тула через HTTP"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "isError": False,
        "content": [
            {
                "type": "text",
                "text": "Search results here"
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    
    with patch.object(http_client, '_get_client', return_value=AsyncMock()) as mock_get_client:
        mock_client = await mock_get_client()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        result = await http_client.call_tool("search_docs", {"query": "test"})
        
        assert result["isError"] is False
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Search results here"


@pytest.mark.asyncio
async def test_call_tool_http_error(http_client):
    """Тест вызова тула с ошибкой"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": "Error: Invalid query"
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    
    with patch.object(http_client, '_get_client', return_value=AsyncMock()) as mock_get_client:
        mock_client = await mock_get_client()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        result = await http_client.call_tool("search_docs", {"query": ""})
        
        assert result["isError"] is True
        assert "Invalid query" in result["content"][0]["text"]


def test_format_mcp_result_text():
    """Тест форматирования текстового результата"""
    content = [
        {"type": "text", "text": "Hello, world!"}
    ]
    
    result = format_mcp_result(content)
    assert result == "Hello, world!"


def test_format_mcp_result_multiple():
    """Тест форматирования нескольких элементов"""
    content = [
        {"type": "text", "text": "First line"},
        {"type": "text", "text": "Second line"}
    ]
    
    result = format_mcp_result(content)
    assert result == "First line\nSecond line"


def test_format_mcp_result_image():
    """Тест форматирования изображения"""
    content = [
        {"type": "image", "mimeType": "image/png"}
    ]
    
    result = format_mcp_result(content)
    assert "Изображение: image/png" in result


def test_format_mcp_result_resource():
    """Тест форматирования ресурса"""
    content = [
        {"type": "resource", "uri": "file:///path/to/file.txt"}
    ]
    
    result = format_mcp_result(content)
    assert "Ресурс: file:///path/to/file.txt" in result


def test_format_mcp_result_empty():
    """Тест форматирования пустого результата"""
    result = format_mcp_result([])
    assert result == "Выполнено успешно"


@pytest.mark.asyncio
async def test_client_close(http_client):
    """Тест закрытия клиента"""
    mock_client = AsyncMock()
    http_client._client = mock_client
    
    await http_client.close()
    
    mock_client.aclose.assert_called_once()
    assert http_client._client is None


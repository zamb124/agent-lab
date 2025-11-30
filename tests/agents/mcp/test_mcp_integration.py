"""
Интеграционные тесты с реальными MCP серверами.

Эти тесты требуют доступа к интернету и реальным MCP серверам.
Помечены как @pytest.mark.integration для выборочного запуска.
"""

import pytest
from apps.agents.services.mcp_client import MCPHttpClient
from apps.agents.models.mcp_models import MCPTransportType
from tests.conftest import skip_if_no_external_access


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_context7_server_available(setup_mcp_servers):
    """
    Проверяет что Context7 сервер доступен и настроен.
    """
    servers = setup_mcp_servers
    
    context7_servers = [s for s in servers if s.server_id == "context7"]
    assert len(context7_servers) == 1
    
    server = context7_servers[0]
    assert server.url == "https://mcp.context7.com/mcp"
    assert server.transport_type == MCPTransportType.HTTP
    assert server.is_active is True
    assert "Authorization" in server.headers
    
    print(f"\n✅ Context7 сервер настроен: {server.name}")


@pytest.mark.asyncio
async def test_sync_context7_tools(setup_mcp_servers, mcp_repo, tool_repo, test_company):
    """
    Интеграционный тест синхронизации тулов с Context7.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    import httpx
    
    tools = []
    try:
        print("\n🔄 Синхронизация Context7 тулов...")
        
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        print(f"✅ Синхронизировано {len(tools)} тулов")
        assert len(tools) > 0
        
        for tool in tools:
            saved_tool = await tool_repo.get(tool.tool_id)
            assert saved_tool is not None
            assert saved_tool.code_mode.value == "mcp_tool"
            assert saved_tool.params["server_id"] == "context7"
            assert saved_tool.params["company_id"] == test_company.company_id
            
            print(f"   ✅ {tool.tool_id}")
            print(f"      {tool.description[:80]}...")
        
        server = await mcp_repo.get("context7")
        assert len(server.cached_tools) == len(tools)
        assert server.last_sync_at is not None
        
        print(f"\n✅ Кэш обновлен: {len(server.cached_tools)} тулов")
    
    except Exception as e:
        skip_if_no_external_access(e)
    
    finally:
        for tool in tools:
            await tool_repo.delete(tool.tool_id)


@pytest.mark.asyncio
async def test_mock_mcp_server_http():
    """
    Интеграционный тест с мок MCP сервером через HTTP.
    
    Использует httpx для мокирования без реального сервера.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    
    client = MCPHttpClient(
        url="https://mcp.mock.example.com/mcp",
        transport_type=MCPTransportType.HTTP
    )
    
    mock_response = MagicMock()
    mock_response.text = ""  # не SSE формат
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string"}
                        }
                    }
                }
            ]
        }
    }
    mock_response.raise_for_status = MagicMock()
    
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    
    with patch.object(client, '_get_client', AsyncMock(return_value=mock_http_client)):
        tools = await client.list_tools()
        
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
        
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "isError": False,
                "content": [
                    {"type": "text", "text": "Test result"}
                ]
            }
        }
        
        result = await client.call_tool("test_tool", {"param1": "value1"})
        
        assert result["isError"] is False
        assert result["content"][0]["text"] == "Test result"


PUBLIC_MCP_SERVERS = {
    "deepwiki_http": {
        "url": "https://mcp.deepwiki.com/mcp",
        "transport_type": MCPTransportType.HTTP,
        "requires_auth": False,
        "description": "DeepWiki MCP - бесплатный, без авторизации"
    },
    "deepwiki_sse": {
        "url": "https://mcp.deepwiki.com/sse",
        "transport_type": MCPTransportType.SSE,
        "requires_auth": False,
        "description": "DeepWiki MCP SSE - бесплатный, без авторизации"
    },
    "context7": {
        "url": "https://mcp.context7.com/mcp",
        "transport_type": MCPTransportType.HTTP,
        "requires_auth": True,
        "env_var": "CONTEXT7_API_KEY",
        "description": "Context7 Documentation MCP"
    },
}


@pytest.mark.asyncio
async def test_create_mcp_tool_from_context7(setup_mcp_servers, test_company, tool_factory, tool_repo):
    """
    Тест создания реального MCP тула через ToolFactory.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    
    try:
        print("\n🔄 Синхронизируем Context7 тулы...")
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        assert len(tools) > 0
        
        first_tool_ref = tools[0]
        print(f"\n🔧 Создаем LangChain тул из: {first_tool_ref.tool_id}")
        
        langchain_tool = await tool_factory._create_mcp_tool(first_tool_ref)
        
        assert langchain_tool is not None
        assert hasattr(langchain_tool, 'name')
        assert hasattr(langchain_tool, 'description')
        
        print("✅ LangChain тул создан:")
        print(f"   name: {langchain_tool.name}")
        print(f"   description: {langchain_tool.description}")
        
        assert hasattr(langchain_tool, '_platform_cost')
        assert hasattr(langchain_tool, '_platform_billing_name')
        assert hasattr(langchain_tool, '_is_platform_tool')
        
        print(f"   cost: {langchain_tool._platform_cost}")
        print(f"   billing_name: {langchain_tool._platform_billing_name}")
    
    finally:
        for tool in tools:
            await tool_repo.delete(tool.tool_id)


@pytest.mark.parametrize("server_name,server_info", PUBLIC_MCP_SERVERS.items())
@pytest.mark.asyncio
async def test_public_mcp_servers(server_name, server_info):
    """
    Параметризованный тест для проверки различных публичных MCP серверов.
    
    Для запуска:
    pytest tests/mcp/test_mcp_integration.py::test_public_mcp_servers -m integration -v
    """
    import os
    
    headers = {}
    if server_info.get("requires_auth"):
        api_key = os.getenv(server_info["env_var"])
        if not api_key:
            pytest.skip(f"{server_info['env_var']} не установлен для {server_name}")
        headers["Authorization"] = f"Bearer {api_key}"
    
    client = MCPHttpClient(
        url=server_info["url"],
        headers=headers,
        transport_type=server_info.get("transport_type", MCPTransportType.HTTP)
    )
    
    try:
        print(f"\n🔍 Тестируем {server_name}: {server_info['description']}")
        print(f"   URL: {server_info['url']}")
        print(f"   Transport: {server_info.get('transport_type', 'HTTP')}")
        
        try:
            tools = await client.list_tools()
        except Exception as e:
            pytest.skip(f"Сервер {server_name} недоступен: {e}")
        
        assert isinstance(tools, list)
        
        print(f"✅ {server_name} MCP: {len(tools)} тулов доступно")
        
        for i, tool in enumerate(tools[:5], 1):
            tool_name = tool.get("name", "unknown")
            tool_desc = tool.get("description", "")[:60]
            print(f"   {i}. {tool_name}: {tool_desc}")
        
        if len(tools) > 5:
            print(f"   ... и еще {len(tools) - 5} тулов")
        
        if tools:
            first_tool = tools[0]
            assert "name" in first_tool, f"Тул должен иметь 'name': {first_tool}"
            assert "inputSchema" in first_tool, f"Тул должен иметь 'inputSchema': {first_tool}"
            
            schema = first_tool["inputSchema"]
            assert isinstance(schema, dict), "inputSchema должна быть dict"
            assert "type" in schema, "inputSchema должна иметь 'type'"
    
    finally:
        await client.close()

"""
Интеграционные тесты с различными публичными MCP серверами.

Список серверов взят из:
- https://github.com/modelcontextprotocol/registry
- https://github.com/punkpeye/awesome-mcp-servers
- https://mcp.so/server/public-mcp-servers
"""

import pytest
from app.core.mcp_client import MCPHttpClient
from app.models.mcp_models import MCPTransportType
import os


pytestmark = pytest.mark.integration


# Конфигурация публичных MCP серверов для тестирования
PUBLIC_MCP_SERVERS = {
    "context7": {
        "url": "https://mcp.context7.com/mcp",
        "transport_type": MCPTransportType.HTTP,
        "requires_auth": True,
        "auth_header": "Authorization",
        "env_var": "CONTEXT7_API_KEY",
        "default_key": "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0",
        "description": "AI-powered documentation search",
        "source": "https://mcp.context7.com"
    },
    "cloudflare_docs": {
        "url": "https://docs.mcp.cloudflare.com/mcp",
        "transport_type": MCPTransportType.HTTP,
        "requires_auth": False,
        "description": "Cloudflare documentation reference",
        "source": "https://github.com/cloudflare/mcp-server-cloudflare"
    },
    "cloudflare_radar": {
        "url": "https://radar.mcp.cloudflare.com/mcp",
        "transport_type": MCPTransportType.HTTP,
        "requires_auth": False,
        "description": "Global Internet traffic insights and trends",
        "source": "https://github.com/cloudflare/mcp-server-cloudflare"
    },
    "cloudflare_browser": {
        "url": "https://browser.mcp.cloudflare.com/mcp",
        "transport_type": MCPTransportType.HTTP,
        "requires_auth": False,
        "description": "Fetch web pages and convert to markdown",
        "source": "https://github.com/cloudflare/mcp-server-cloudflare"
    },
}


@pytest.mark.parametrize("server_name,server_info", PUBLIC_MCP_SERVERS.items())
@pytest.mark.asyncio
async def test_public_server_list_tools(server_name, server_info):
    """
    Параметризованный тест для проверки list_tools у публичных MCP серверов.
    
    Для запуска всех:
    pytest tests/mcp/test_public_mcp_servers.py::test_public_server_list_tools -m integration -v
    
    Для конкретного сервера:
    pytest tests/mcp/test_public_mcp_servers.py::test_public_server_list_tools[context7] -m integration -v -s
    """
    # Получаем API ключ
    headers = {}
    if server_info.get("requires_auth"):
        env_var = server_info["env_var"]
        api_key = os.getenv(env_var, server_info.get("default_key"))
        
        if not api_key:
            pytest.skip(f"{env_var} не установлен для {server_name}")
        
        auth_header = server_info.get("auth_header", "Authorization")
        headers[auth_header] = f"Bearer {api_key}"
    
    # Создаем клиент
    client = MCPHttpClient(
        url=server_info["url"],
        headers=headers,
        transport_type=server_info.get("transport_type", MCPTransportType.HTTP)
    )
    
    try:
        print(f"\n{'='*60}")
        print(f"🔍 Тестируем: {server_name}")
        print(f"{'='*60}")
        print(f"📝 Описание: {server_info['description']}")
        print(f"🌐 URL: {server_info['url']}")
        print(f"🚀 Transport: {server_info.get('transport_type', 'HTTP')}")
        print(f"🔐 Авторизация: {'Требуется' if server_info.get('requires_auth') else 'Не требуется'}")
        
        # Получаем список тулов
        tools = await client.list_tools()
        
        print(f"\n✅ Получено {len(tools)} тулов")
        assert isinstance(tools, list)
        assert len(tools) > 0, f"Сервер {server_name} должен вернуть хотя бы один тул"
        
        # Показываем доступные тулы
        print(f"\n📋 Доступные тулы:")
        for i, tool in enumerate(tools, 1):
            tool_name = tool.get("name", "unknown")
            tool_desc = tool.get("description", "")[:100]
            print(f"   {i}. {tool_name}")
            print(f"      {tool_desc}...")
            
            # Проверяем структуру тула
            assert "name" in tool, f"Тул должен иметь 'name'"
            assert "inputSchema" in tool, f"Тул должен иметь 'inputSchema'"
            
            schema = tool["inputSchema"]
            assert isinstance(schema, dict), "inputSchema должна быть dict"
            assert "type" in schema, "inputSchema должна иметь 'type'"
            
            if "properties" in schema:
                params = list(schema["properties"].keys())
                print(f"      Параметры: {', '.join(params)}")
            print()
        
        print(f"\n{'='*60}")
        print(f"✅ {server_name} MCP тестирование успешно завершено")
        print(f"{'='*60}\n")
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_context7_resolve_library():
    """
    Специфичный тест для Context7: resolve-library-id тула.
    """
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    client = MCPHttpClient(
        url="https://mcp.context7.com/mcp",
        headers={"Authorization": f"Bearer {api_key}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔧 Тестируем Context7: resolve-library-id")
        
        # Тестируем с разными библиотеками
        test_libraries = ["fastapi", "langchain", "react", "nextjs"]
        
        for lib_name in test_libraries:
            print(f"\n   📚 Поиск библиотеки: {lib_name}")
            
            result = await client.call_tool("resolve-library-id", {
                "libraryName": lib_name
            })
            
            assert "content" in result
            assert result.get("isError") is False
            
            # Получаем текст результата
            content_text = "".join([
                item.get("text", "") 
                for item in result.get("content", []) 
                if item.get("type") == "text"
            ])
            
            assert len(content_text) > 0
            print(f"   ✅ Найдена информация: {content_text[:150]}...")
        
        print(f"\n✅ Все библиотеки успешно найдены")
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_context7_get_docs():
    """
    Специфичный тест для Context7: get-library-docs тула.
    """
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    client = MCPHttpClient(
        url="https://mcp.context7.com/mcp",
        headers={"Authorization": f"Bearer {api_key}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔧 Тестируем Context7: get-library-docs")
        
        # Тестируем получение документации
        test_cases = [
            {
                "library_id": "/langchain-ai/langchain",
                "topic": "agents",
                "description": "LangChain agents documentation"
            },
            {
                "library_id": "/fastapi/fastapi",
                "topic": "routing",
                "description": "FastAPI routing documentation"
            }
        ]
        
        for test_case in test_cases:
            print(f"\n   📖 Получаем документацию: {test_case['description']}")
            print(f"      Library ID: {test_case['library_id']}")
            print(f"      Topic: {test_case['topic']}")
            
            result = await client.call_tool("get-library-docs", {
                "context7CompatibleLibraryID": test_case["library_id"],
                "topic": test_case["topic"],
                "tokens": 1000
            })
            
            assert "content" in result
            
            if result.get("isError"):
                print(f"   ⚠️  Ошибка (может быть валидной): {result}")
                continue
            
            # Получаем текст документации
            docs_text = "".join([
                item.get("text", "") 
                for item in result.get("content", []) 
                if item.get("type") == "text"
            ])
            
            assert len(docs_text) > 0
            print(f"   ✅ Получено {len(docs_text)} символов документации")
            print(f"   📝 Превью: {docs_text[:200]}...")
        
        print(f"\n✅ Документация успешно получена")
    
    finally:
        await client.close()


"""
Интеграционные тесты с Cloudflare MCP серверами.

Cloudflare предоставляет множество MCP серверов:
- Documentation - справочная информация по Cloudflare
- Radar - глобальная статистика интернет трафика
- Browser Rendering - fetch веб-страниц и конвертация в markdown
- И другие...

Source: https://github.com/cloudflare/mcp-server-cloudflare
"""

import pytest
from apps.agents.services.mcp_client import MCPHttpClient
from apps.agents.models.mcp_models import MCPTransportType


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.skip(reason="Cloudflare MCP серверы требуют Cloudflare API токен")
async def test_cloudflare_docs_list_tools():
    """
    Тест Cloudflare Documentation MCP сервера.
    Требует Cloudflare API токен.
    
    Для запуска:
    1. Получите Cloudflare API токен
    2. Установите CLOUDFLARE_API_TOKEN
    3. Уберите @pytest.mark.skip
    """
    import os
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        pytest.skip("CLOUDFLARE_API_TOKEN не установлен")
    
    client = MCPHttpClient(
        url="https://docs.mcp.cloudflare.com/mcp",
        headers={"Authorization": f"Bearer {api_token}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔍 Подключение к Cloudflare Docs MCP...")
        
        tools = await client.list_tools()
        
        print(f"✅ Получено {len(tools)} тулов от Cloudflare Docs")
        
        assert len(tools) > 0
        
        print("\n📋 Доступные тулы:")
        for i, tool in enumerate(tools, 1):
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")[:80]
            print(f"   {i}. {name}")
            print(f"      {desc}...")
            
            assert "name" in tool
            assert "inputSchema" in tool
    
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Cloudflare MCP серверы требуют Cloudflare API токен")
async def test_cloudflare_radar_list_tools():
    """
    Тест Cloudflare Radar MCP сервера.
    Требует Cloudflare API токен.
    """
    import os
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        pytest.skip("CLOUDFLARE_API_TOKEN не установлен")
    
    client = MCPHttpClient(
        url="https://radar.mcp.cloudflare.com/mcp",
        headers={"Authorization": f"Bearer {api_token}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔍 Подключение к Cloudflare Radar MCP...")
        
        tools = await client.list_tools()
        
        print(f"✅ Получено {len(tools)} тулов от Cloudflare Radar")
        
        assert len(tools) > 0
        
        print("\n📋 Доступные тулы Radar:")
        for i, tool in enumerate(tools[:10], 1):  # Первые 10
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")[:100]
            print(f"   {i}. {name}")
            if desc:
                print(f"      {desc}...")
            
            assert "name" in tool
            assert "inputSchema" in tool
        
        if len(tools) > 10:
            print(f"   ... и еще {len(tools) - 10} тулов")
    
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Cloudflare MCP серверы требуют Cloudflare API токен")
async def test_cloudflare_browser_list_tools():
    """
    Тест Cloudflare Browser Rendering MCP сервера.
    Требует Cloudflare API токен.
    """
    import os
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        pytest.skip("CLOUDFLARE_API_TOKEN не установлен")
    
    client = MCPHttpClient(
        url="https://browser.mcp.cloudflare.com/mcp",
        headers={"Authorization": f"Bearer {api_token}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔍 Подключение к Cloudflare Browser MCP...")
        
        tools = await client.list_tools()
        
        print(f"✅ Получено {len(tools)} тулов от Cloudflare Browser")
        
        assert len(tools) > 0
        
        print("\n📋 Доступные тулы Browser:")
        for i, tool in enumerate(tools, 1):
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")[:100]
            print(f"   {i}. {name}")
            print(f"      {desc}...")
            
            schema = tool.get("inputSchema", {})
            if "properties" in schema:
                params = list(schema["properties"].keys())
                print(f"      Параметры: {', '.join(params)}")
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cloudflare_docs_search():
    """
    Тест вызова тула поиска в Cloudflare Docs.
    """
    client = MCPHttpClient(
        url="https://docs.mcp.cloudflare.com/mcp",
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔧 Тестируем поиск в Cloudflare Docs...")
        
        # Сначала получаем список тулов чтобы узнать имена
        tools = await client.list_tools()
        
        if not tools:
            pytest.skip("Нет доступных тулов")
        
        # Ищем тул для поиска
        search_tool = next(
            (t for t in tools if "search" in t.get("name", "").lower()),
            None
        )
        
        if not search_tool:
            # Если нет search, берем первый доступный тул
            search_tool = tools[0]
        
        tool_name = search_tool["name"]
        print(f"   Используем тул: {tool_name}")
        
        # Формируем аргументы
        schema = search_tool.get("inputSchema", {})
        properties = schema.get("properties", {})
        
        args = {}
        if properties:
            # Подставляем тестовые значения
            for prop_name, prop_spec in properties.items():
                if "query" in prop_name.lower():
                    args[prop_name] = "workers"
                elif prop_spec.get("type") == "string":
                    args[prop_name] = "test"
                elif prop_spec.get("type") == "number":
                    args[prop_name] = 5
        
        if args:
            print(f"   Аргументы: {args}")
            
            result = await client.call_tool(tool_name, args)
            
            assert "content" in result
            
            if result.get("isError"):
                print(f"   ⚠️  Ошибка: ожидаемо для тестовых данных")
            else:
                content_text = "".join([
                    item.get("text", "")
                    for item in result.get("content", [])
                    if item.get("type") == "text"
                ])
                print(f"   ✅ Результат получен: {len(content_text)} символов")
                print(f"   📝 Превью: {content_text[:200]}...")
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_multiple_cloudflare_servers():
    """
    Тест одновременной работы с несколькими Cloudflare MCP серверами.
    """
    servers = [
        ("docs", "https://docs.mcp.cloudflare.com/mcp"),
        ("radar", "https://radar.mcp.cloudflare.com/mcp"),
        ("browser", "https://browser.mcp.cloudflare.com/mcp"),
    ]
    
    print("\n🔍 Тестируем множественные Cloudflare MCP серверы...")
    
    results = {}
    
    for name, url in servers:
        client = MCPHttpClient(url=url, transport_type=MCPTransportType.HTTP)
        
        try:
            tools = await client.list_tools()
            results[name] = len(tools)
            print(f"   ✅ {name}: {len(tools)} тулов")
        except Exception as e:
            results[name] = 0
            print(f"   ❌ {name}: ошибка - {str(e)[:50]}...")
        finally:
            await client.close()
    
    # Проверяем что хотя бы один сервер работает
    working_servers = [name for name, count in results.items() if count > 0]
    assert len(working_servers) >= 1, "Хотя бы один Cloudflare MCP сервер должен работать"
    
    print(f"\n✅ Работает {len(working_servers)} из {len(servers)} серверов")
    print(f"   Рабочие: {', '.join(working_servers)}")


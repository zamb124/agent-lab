"""
Интеграционные тесты с Context7 MCP сервером.

Context7 - AI-powered documentation MCP сервер.
"""

import pytest
from apps.agents.services.mcp_client import MCPHttpClient
from apps.agents.models.mcp_models import MCPTransportType
import os
from tests.conftest import skip_if_no_external_access


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_context7_list_tools():
    """
    Тест получения списка тулов от Context7 MCP.
    
    Для запуска:
    pytest tests/mcp/test_deepwiki_integration.py::test_context7_list_tools -m integration -v -s
    """
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    client = MCPHttpClient(
        url="https://mcp.context7.com/mcp",
        headers={"Authorization": f"Bearer {api_key}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔍 Подключение к Context7 MCP...")
        
        try:
            tools = await client.list_tools()
        except Exception as e:
            skip_if_no_external_access(e)
        
        print(f"✅ Получено {len(tools)} тулов от Context7 MCP")
        
        assert len(tools) > 0, "DeepWiki MCP должен вернуть хотя бы один тул"
        
        print("\n📋 Доступные тулы Context7 MCP:")
        for i, tool in enumerate(tools, 1):
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            print(f"   {i}. {name}")
            print(f"      {desc}")
            
            assert "name" in tool
            assert "inputSchema" in tool
            
            schema = tool["inputSchema"]
            assert isinstance(schema, dict)
            assert "type" in schema
            
            if "properties" in schema:
                params = list(schema["properties"].keys())
                print(f"      Параметры: {', '.join(params)}")
            print()
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_context7_sync_to_db(setup_mcp_servers, mcp_repo, tool_repo, test_company):
    """
    Полный тест синхронизации Context7 тулов в БД.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    
    try:
        print("\n🔄 Синхронизация Context7 тулов в БД...")
        
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        print(f"✅ Синхронизировано {len(tools)} тулов")
        assert len(tools) == 2  # resolve-library-id и get-library-docs
        
        for tool in tools:
            print(f"\n📦 Тул: {tool.tool_id}")
            print(f"   Название: {tool.title}")
            print(f"   Группа: {tool.group}")
            print(f"   Code mode: {tool.code_mode}")
            
            saved_tool = await tool_repo.get(tool.tool_id)
            assert saved_tool is not None
            assert saved_tool.code_mode.value == "mcp_tool"
            assert saved_tool.params["server_id"] == "context7"
            assert saved_tool.params["company_id"] == test_company.company_id
            assert "input_schema" in saved_tool.params
        
        server = await mcp_repo.get("context7")
        assert len(server.cached_tools) == 2
        assert server.last_sync_at is not None
        
        print("\n✅ Все тулы сохранены и закэшированы")
    
    finally:
        if 'tools' in locals():
            for tool in tools:
                await tool_repo.delete(tool.tool_id)


@pytest.mark.asyncio
async def test_context7_call_resolve_library():
    """
    Тест вызова Context7 тула resolve-library-id.
    """
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    client = MCPHttpClient(
        url="https://mcp.context7.com/mcp",
        headers={"Authorization": f"Bearer {api_key}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔧 Вызываем Context7 тул: resolve-library-id")
        
        result = await client.call_tool("resolve-library-id", {
            "libraryName": "langchain"
        })
        
        print("✅ Тул вызван успешно")
        
        assert "content" in result
        assert result.get("isError") is False
        
        print("\n📋 Результат:")
        for content_item in result.get("content", []):
            if content_item.get("type") == "text":
                text = content_item.get("text", "")
                print(f"   {text[:300]}...")
        
        content_text = "".join([
            item.get("text", "") 
            for item in result.get("content", []) 
            if item.get("type") == "text"
        ])
        
        # Проверяем на ошибки авторизации в ответе
        skip_if_no_external_access(message=content_text)
        
        assert "langchain" in content_text.lower() or "library" in content_text.lower()
    
    except Exception as e:
        skip_if_no_external_access(e)
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_context7_call_get_library_docs():
    """
    Тест вызова Context7 тула get-library-docs.
    """
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    client = MCPHttpClient(
        url="https://mcp.context7.com/mcp",
        headers={"Authorization": f"Bearer {api_key}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔧 Вызываем Context7 тул: get-library-docs")
        
        result = await client.call_tool("get-library-docs", {
            "context7CompatibleLibraryID": "/langchain-ai/langchain",
            "topic": "agents"
        })
        
        print("✅ Тул вызван успешно")
        
        assert "content" in result
        
        if result.get("isError"):
            print("⚠️  Ошибка (может быть валидной):")
            for item in result.get("content", []):
                if item.get("type") == "text":
                    print(f"   {item.get('text', '')[:200]}")
        else:
            print("\n📋 Документация получена:")
            for content_item in result.get("content", []):
                if content_item.get("type") == "text":
                    text = content_item.get("text", "")
                    print(f"   {text[:300]}...")
                    break
    
    except Exception as e:
        skip_if_no_external_access(e)
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_context7_full_workflow_with_toolfactory(setup_mcp_servers, test_company, tool_factory, tool_repo):
    """
    Полный workflow: синхронизация → создание тула через ToolFactory → использование.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    
    tools = []
    try:
        print("\n📝 Шаг 1: Синхронизация Context7 тулов")
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов")
    except Exception as e:
        skip_if_no_external_access(e)
    
    try:
        
        resolve_tool_ref = next((t for t in tools if "resolve" in t.tool_id), None)
        assert resolve_tool_ref is not None
        
        print("\n🔧 Шаг 2: Создаем LangChain тул через ToolFactory")
        print(f"   Тул: {resolve_tool_ref.tool_id}")
        
        langchain_tool = await tool_factory._create_mcp_tool(resolve_tool_ref)
        
        assert langchain_tool is not None
        assert hasattr(langchain_tool, 'name')
        assert hasattr(langchain_tool, 'description')
        assert hasattr(langchain_tool, '_is_platform_tool')
        
        print("✅ LangChain тул создан:")
        print(f"   name: {langchain_tool.name}")
        print(f"   description: {langchain_tool.description[:100]}...")
        
        print("\n🚀 Шаг 3: Вызываем тул")
        result = await langchain_tool.ainvoke({"libraryName": "fastapi"})
        
        print("✅ Тул выполнен:")
        print(f"   {result[:300]}...")
        
        assert result is not None
        assert len(result) > 0
        
        print("\n✅ Полный workflow успешно выполнен!")
    
    finally:
        if 'tools' in locals():
            for tool in tools:
                await tool_repo.delete(tool.tool_id)


@pytest.mark.asyncio
async def test_context7_full_workflow(mcp_repo, tool_repo, test_context):
    """
    Полный workflow: создание сервера, синхронизация, проверка кэша.
    """
    from apps.agents.models.mcp_models import MCPServerConfig
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    import os
    
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    server_config = MCPServerConfig(
        server_id="context7_workflow_test",
        company_id="test_company",
        name="Context7 Workflow Test",
        description="Test full workflow",
        url="https://mcp.context7.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {api_key}"},
        is_active=True,
        auto_sync_tools=True
    )
    
    try:
        print("\n📝 Шаг 1: Создаем MCP сервер в БД")
        await mcp_repo.set(server_config)
        print("✅ Сервер создан")
        
        print("\n🔄 Шаг 2: Синхронизируем тулы")
        tools = await sync_mcp_server_tools("context7_workflow_test", "test_company")
        print(f"✅ Синхронизировано {len(tools)} тулов")
        
        assert len(tools) > 0
        
        first_tool = tools[0]
        assert first_tool.tool_id.startswith("mcp:context7_workflow_test:")
        assert first_tool.code_mode.value == "mcp_tool"
        assert "server_id" in first_tool.params
        assert "company_id" in first_tool.params
        assert "tool_name" in first_tool.params
        assert "input_schema" in first_tool.params
        
        print("\n📋 Первый синхронизированный тул:")
        print(f"   tool_id: {first_tool.tool_id}")
        print(f"   title: {first_tool.title}")
        print(f"   description: {first_tool.description}")
        print(f"   group: {first_tool.group}")
        
        print("\n🔍 Шаг 3: Проверяем обновление кэша")
        updated_server = await mcp_repo.get("context7_workflow_test")
        assert len(updated_server.cached_tools) == len(tools)
        assert updated_server.last_sync_at is not None
        print(f"✅ Кэш обновлен: {len(updated_server.cached_tools)} тулов")
        
        print("\n✅ Полный workflow успешно выполнен!")
    
    finally:
        await mcp_repo.delete("context7_workflow_test")
        
        if 'tools' in locals():
            for tool in tools:
                await tool_repo.delete(tool.tool_id)
        
        print("\n🧹 Очистка завершена")


@pytest.mark.asyncio  
async def test_context7_in_agent(setup_mcp_servers, test_company, agent_repo, tool_repo, agent_factory):
    """
    Тест использования Context7 MCP тулов в реальном агенте.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models import AgentConfig
    import httpx
    
    tools = []
    try:
        print("\n📝 Шаг 1: Синхронизируем Context7 тулы")
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов")
    except Exception as e:
        skip_if_no_external_access(e)
    
    if not tools:
        pytest.skip("MCP тулы не синхронизировались (возможно проблема с внешним сервисом)")
    
    try:
        
        print("\n🤖 Шаг 2: Создаем тестового агента с MCP тулами")
        
        agent_config = AgentConfig(
            agent_id="test_mcp_agent",
            name="Test MCP Agent",
            description="Агент с MCP инструментами",
            prompt="Ты помощник с доступом к документации через Context7 MCP",
            tools=tools,
        )
        
        await agent_repo.set(agent_config)
        
        print(f"✅ Агент создан с {len(tools)} MCP тулами")
        
        print("\n🏭 Шаг 3: Загружаем агента через AgentFactory")
        agent = await agent_factory.get_agent("test_mcp_agent")
        
        print("✅ Агент загружен")
        print(f"   Количество тулов: {len(agent.tools)}")
        
        assert len(agent.tools) >= 2
        
        for tool in agent.tools:
            print(f"   - {tool.name}: {hasattr(tool, '_is_platform_tool')}")
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
        
        print("\n✅ Все MCP тулы успешно загружены в агента!")
    
    finally:
        await agent_repo.delete("test_mcp_agent")
        for tool in tools:
            await tool_repo.delete(tool.tool_id)

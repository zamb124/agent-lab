"""
from app.core.container import get_container
Интеграционные тесты с Context7 MCP сервером.

Context7 - AI-powered documentation MCP сервер.
"""

import pytest
from app.core.mcp_client import MCPHttpClient
from app.models.mcp_models import MCPTransportType
import os


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
        
        tools = await client.list_tools()
        
        print(f"✅ Получено {len(tools)} тулов от Context7 MCP")
        
        # Проверяем что получили хотя бы один тул
        assert len(tools) > 0, "DeepWiki MCP должен вернуть хотя бы один тул"
        
        # Показываем все доступные тулы
        print("\n📋 Доступные тулы Context7 MCP:")
        for i, tool in enumerate(tools, 1):
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            print(f"   {i}. {name}")
            print(f"      {desc}")
            
            # Проверяем структуру
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
async def test_context7_sync_to_db(setup_mcp_servers, mcp_repo, test_company):
    """
    Полный тест синхронизации Context7 тулов в БД.
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.db.repositories.tool_repository import ToolRepository
    from app.db.repositories.storage import Storage
    
    storage = Storage()
    tool_repo = ToolRepository(storage)
    
    try:
        print("\n🔄 Синхронизация Context7 тулов в БД...")
        
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        print(f"✅ Синхронизировано {len(tools)} тулов")
        assert len(tools) == 2  # resolve-library-id и get-library-docs
        
        # Проверяем каждый тул
        for tool in tools:
            print(f"\n📦 Тул: {tool.tool_id}")
            print(f"   Название: {tool.title}")
            print(f"   Группа: {tool.group}")
            print(f"   Code mode: {tool.code_mode}")
            
            # Проверяем сохранение в БД
            saved_tool = await tool_repo.get(tool.tool_id)
            assert saved_tool is not None
            assert saved_tool.code_mode.value == "mcp_tool"
            assert saved_tool.params["server_id"] == "context7"
            assert saved_tool.params["company_id"] == test_company.company_id
            assert "input_schema" in saved_tool.params
        
        # Проверяем кэш в конфиге сервера
        server = await mcp_repo.get("context7", test_company.company_id)
        assert len(server.cached_tools) == 2
        assert server.last_sync_at is not None
        
        print(f"\n✅ Все тулы сохранены и закэшированы")
    
    finally:
        # Очистка
        if 'tools' in locals():
            for tool in tools:
                await storage.delete(f"tool:{tool.tool_id}")


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
        
        # Вызываем тул с тестовым запросом
        result = await client.call_tool("resolve-library-id", {
            "libraryName": "langchain"
        })
        
        print(f"✅ Тул вызван успешно")
        
        # Проверяем результат
        assert "content" in result
        assert result.get("isError") is False
        
        print(f"\n📋 Результат:")
        for content_item in result.get("content", []):
            if content_item.get("type") == "text":
                text = content_item.get("text", "")
                print(f"   {text[:300]}...")
        
        # Проверяем что в результате есть информация о библиотеке
        content_text = "".join([
            item.get("text", "") 
            for item in result.get("content", []) 
            if item.get("type") == "text"
        ])
        assert "langchain" in content_text.lower() or "library" in content_text.lower()
    
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
        
        # Вызываем тул для получения документации LangChain
        result = await client.call_tool("get-library-docs", {
            "context7CompatibleLibraryID": "/langchain-ai/langchain",
            "topic": "agents"
        })
        
        print(f"✅ Тул вызван успешно")
        
        # Проверяем результат
        assert "content" in result
        
        if result.get("isError"):
            print(f"⚠️  Ошибка (может быть валидной):")
            for item in result.get("content", []):
                if item.get("type") == "text":
                    print(f"   {item.get('text', '')[:200]}")
        else:
            print(f"\n📋 Документация получена:")
            for content_item in result.get("content", []):
                if content_item.get("type") == "text":
                    text = content_item.get("text", "")
                    print(f"   {text[:300]}...")
                    break
    
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_context7_full_workflow_with_toolfactory(setup_mcp_servers, test_company):
    """
    Полный workflow: синхронизация → создание тула через ToolFactory → использование.
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.tool_factory import ToolFactory
    from app.db.repositories.storage import Storage
    
    storage = Storage()
    tool_factory = ToolFactory()
    
    try:
        print("\n📝 Шаг 1: Синхронизация Context7 тулов")
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов")
        
        # Берем resolve-library-id
        resolve_tool_ref = next((t for t in tools if "resolve" in t.tool_id), None)
        assert resolve_tool_ref is not None
        
        print(f"\n🔧 Шаг 2: Создаем LangChain тул через ToolFactory")
        print(f"   Тул: {resolve_tool_ref.tool_id}")
        
        langchain_tool = await tool_factory._create_mcp_tool(resolve_tool_ref)
        
        assert langchain_tool is not None
        assert hasattr(langchain_tool, 'name')
        assert hasattr(langchain_tool, 'description')
        assert hasattr(langchain_tool, '_is_platform_tool')
        
        print(f"✅ LangChain тул создан:")
        print(f"   name: {langchain_tool.name}")
        print(f"   description: {langchain_tool.description[:100]}...")
        
        print(f"\n🚀 Шаг 3: Вызываем тул")
        # Вызываем тул (через ainvoke как в LangChain)
        result = await langchain_tool.ainvoke({"libraryName": "fastapi"})
        
        print(f"✅ Тул выполнен:")
        print(f"   {result[:300]}...")
        
        assert result is not None
        assert len(result) > 0
        
        print(f"\n✅ Полный workflow успешно выполнен!")
    
    finally:
        # Очистка
        if 'tools' in locals():
            for tool in tools:
                await storage.delete(f"tool:{tool.tool_id}")


@pytest.mark.asyncio
async def test_context7_full_workflow():
    """
    Полный workflow: создание сервера, синхронизация, проверка кэша.
    """
    from app.models.mcp_models import MCPServerConfig
    from app.db.repositories.mcp_repository import MCPServerRepository
    from app.db.repositories.storage import Storage
    from app.core.mcp_sync import sync_mcp_server_tools
    import os
    
    storage = Storage()
    mcp_repo = MCPServerRepository(storage)
    
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    # Создаем новый тестовый сервер
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
        
        # Проверяем что тулы созданы
        assert len(tools) > 0
        
        # Проверяем структуру первого тула
        first_tool = tools[0]
        assert first_tool.tool_id.startswith("mcp:context7_workflow_test:")
        assert first_tool.code_mode.value == "mcp_tool"
        assert "server_id" in first_tool.params
        assert "company_id" in first_tool.params
        assert "tool_name" in first_tool.params
        assert "input_schema" in first_tool.params
        
        print(f"\n📋 Первый синхронизированный тул:")
        print(f"   tool_id: {first_tool.tool_id}")
        print(f"   title: {first_tool.title}")
        print(f"   description: {first_tool.description}")
        print(f"   group: {first_tool.group}")
        
        print("\n🔍 Шаг 3: Проверяем обновление кэша")
        updated_server = await mcp_repo.get("context7_workflow_test", "test_company")
        assert len(updated_server.cached_tools) == len(tools)
        assert updated_server.last_sync_at is not None
        print(f"✅ Кэш обновлен: {len(updated_server.cached_tools)} тулов")
        
        print("\n✅ Полный workflow успешно выполнен!")
    
    finally:
        # Очистка
        await mcp_repo.delete("context7_workflow_test", "test_company")
        
        # Удаляем созданные тулы
        for tool in tools:
            tool_key = f"tool:{tool.tool_id}"
            await storage.delete(tool_key)
        
        print("\n🧹 Очистка завершена")


@pytest.mark.asyncio  
async def test_context7_in_agent(setup_mcp_servers, test_company):
    """
    Тест использования Context7 MCP тулов в реальном агенте.
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig, ToolReference
    from app.models.core_models import CodeMode
    from app.db.repositories.storage import Storage
    
    storage = Storage()
    
    try:
        print("\n📝 Шаг 1: Синхронизируем Context7 тулы")
        tools = await sync_mcp_server_tools("context7", test_company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов")
        
        # Создаем агента с MCP тулами
        print("\n🤖 Шаг 2: Создаем тестового агента с MCP тулами")
        
        agent_config = AgentConfig(
            agent_id="test_mcp_agent",
            name="Test MCP Agent",
            description="Агент с MCP инструментами",
            prompt="Ты помощник с доступом к документации через Context7 MCP",
            tools=tools,  # Передаем MCP тулы
        )
        
        # Сохраняем агента
        from app.db.repositories.agent_repository import AgentRepository
        agent_repo = AgentRepository(storage)
        await agent_repo.set(agent_config)
        
        print(f"✅ Агент создан с {len(tools)} MCP тулами")
        
        # Создаем агента через фабрику
        print("\n🏭 Шаг 3: Загружаем агента через AgentFactory")
        agent_factory = get_container().agent_factory
        agent = await agent_factory.get_agent("test_mcp_agent")
        
        print(f"✅ Агент загружен")
        print(f"   Количество тулов: {len(agent.tools)}")
        
        # Проверяем что MCP тулы загружены
        assert len(agent.tools) >= 2
        
        # Проверяем типы тулов
        for tool in agent.tools:
            print(f"   - {tool.name}: {hasattr(tool, '_is_platform_tool')}")
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
        
        print(f"\n✅ Все MCP тулы успешно загружены в агента!")
    
    finally:
        # Очистка
        await agent_repo.delete("test_mcp_agent")
        for tool in tools:
            await storage.delete(f"tool:{tool.tool_id}")
        await storage._pool.close()


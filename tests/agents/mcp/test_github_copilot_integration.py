"""
Интеграционные тесты с GitHub Copilot MCP сервером.

GitHub Copilot MCP - сервер для работы с AI-ассистентом GitHub.
"""

import pytest
from apps.agents.services.mcp_client import MCPHttpClient
from apps.agents.models.mcp_models import MCPTransportType
import os


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_github_copilot_list_tools():
    """
    Тест получения списка тулов от GitHub Copilot MCP.
    
    Для запуска:
    pytest tests/mcp/test_github_copilot_integration.py::test_github_copilot_list_tools -m integration -v -s
    """
    api_key = os.getenv("GITHUB_COPILOT_TOKEN")
    if not api_key:
        pytest.skip("GITHUB_COPILOT_TOKEN not set")
    
    client = MCPHttpClient(
        url="https://api.githubcopilot.com/mcp",
        headers={"Authorization": f"Bearer {api_key}"},
        transport_type=MCPTransportType.HTTP
    )
    
    try:
        print("\n🔍 Подключение к GitHub Copilot MCP...")
        
        tools = await client.list_tools()
        
        print(f"✅ Получено {len(tools)} тулов от GitHub Copilot MCP")
        
        assert len(tools) > 0, "GitHub Copilot MCP должен вернуть хотя бы один тул"
        
        print("\n📋 Доступные тулы GitHub Copilot MCP:")
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
async def test_github_copilot_sync_to_db(mcp_repo, tool_repo, test_company):
    """
    Полный тест синхронизации GitHub Copilot тулов в БД.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    import os
    
    api_key = os.getenv("GITHUB_COPILOT_TOKEN")
    if not api_key:
        pytest.skip("GITHUB_COPILOT_TOKEN not set")
    
    server_config = MCPServerConfig(
        server_id="github_copilot",
        company_id=test_company.company_id,
        name="GitHub Copilot MCP",
        description="GitHub Copilot AI-ассистент",
        url="https://api.githubcopilot.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {api_key}"},
        is_active=True,
        auto_sync_tools=True
    )
    
    await mcp_repo.set(server_config)
    
    try:
        print("\n🔄 Синхронизация GitHub Copilot тулов в БД...")
        
        tools = await sync_mcp_server_tools("github_copilot", test_company.company_id)
        
        print(f"✅ Синхронизировано {len(tools)} тулов")
        assert len(tools) > 0
        
        for tool in tools:
            print(f"\n📦 Тул: {tool.tool_id}")
            print(f"   Название: {tool.title}")
            print(f"   Группа: {tool.group}")
            print(f"   Code mode: {tool.code_mode}")
            
            saved_tool = await tool_repo.get(tool.tool_id)
            assert saved_tool is not None
            assert saved_tool.code_mode.value == "mcp_tool"
            assert saved_tool.params["server_id"] == "github_copilot"
            assert saved_tool.params["company_id"] == test_company.company_id
            assert "input_schema" in saved_tool.params
        
        server = await mcp_repo.get("github_copilot")
        assert len(server.cached_tools) == len(tools)
        assert server.last_sync_at is not None
        
        print("\n✅ Все тулы сохранены и закэшированы")
    
    finally:
        if 'tools' in locals():
            for tool in tools:
                await tool_repo.delete(tool.tool_id)
        await mcp_repo.delete("github_copilot")


@pytest.mark.asyncio
async def test_github_copilot_in_agent(mcp_repo, agent_repo, tool_repo, agent_factory, test_company):
    """
    Тест использования GitHub Copilot MCP тулов в реальном агенте.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models import AgentConfig
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    from apps.agents.tools.misc.standard import ask_user
    import os
    
    api_key = os.getenv("GITHUB_COPILOT_TOKEN")
    if not api_key:
        pytest.skip("GITHUB_COPILOT_TOKEN not set")
    
    server_config = MCPServerConfig(
        server_id="github_copilot",
        company_id=test_company.company_id,
        name="GitHub Copilot MCP",
        url="https://api.githubcopilot.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {api_key}"},
        is_active=True
    )
    
    await mcp_repo.set(server_config)
    
    try:
        print("\n📝 Шаг 1: Синхронизируем GitHub Copilot тулы")
        tools = await sync_mcp_server_tools("github_copilot", test_company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов")
        
        print("\n🤖 Шаг 2: Создаем тестового агента с MCP тулами")
        
        agent_config = AgentConfig(
            agent_id="test_github_copilot_agent",
            name="GitHub Copilot Agent",
            description="Агент с GitHub Copilot инструментами",
            prompt="""
Ты помощник-разработчик с доступом к GitHub Copilot.

Используй GitHub Copilot тулы для помощи с кодом:
- Генерация кода
- Объяснение кода
- Рефакторинг
- Документация
""",
            tools=[
                ask_user,
                *tools,
            ]
        )
        
        await agent_repo.set(agent_config)
        
        print(f"✅ Агент создан с {len(tools)} MCP тулами")
        
        print("\n🏭 Шаг 3: Загружаем агента через AgentFactory")
        agent = await agent_factory.get_agent("test_github_copilot_agent")
        
        print("✅ Агент загружен")
        print(f"   Количество тулов: {len(agent.tools)}")
        
        loaded_tools = await agent.get_tools()
        assert len(loaded_tools) >= len(tools)
        
        for tool in loaded_tools:
            print(f"   - {tool.name}")
        
        print("\n✅ Все GitHub Copilot MCP тулы успешно загружены в агента!")
    
    finally:
        await agent_repo.delete("test_github_copilot_agent")
        if 'tools' in locals():
            for tool in tools:
                await tool_repo.delete(tool.tool_id)
        await mcp_repo.delete("github_copilot")


@pytest.mark.asyncio
async def test_github_copilot_full_workflow(test_company, mcp_repo, tool_repo, test_context):
    """
    Полный workflow: создание сервера, синхронизация, проверка кэша.
    """
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    import os
    
    api_key = os.getenv("GITHUB_COPILOT_TOKEN")
    if not api_key:
        pytest.skip("GITHUB_COPILOT_TOKEN not set")
    
    server_config = MCPServerConfig(
        server_id="github_copilot_workflow_test",
        company_id=test_company.company_id,
        name="GitHub Copilot Workflow Test",
        description="Test full workflow",
        url="https://api.githubcopilot.com/mcp",
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
        tools = await sync_mcp_server_tools("github_copilot_workflow_test", test_company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов")
        
        assert len(tools) > 0
        
        first_tool = tools[0]
        assert first_tool.tool_id.startswith("mcp:github_copilot_workflow_test:")
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
        updated_server = await mcp_repo.get("github_copilot_workflow_test")
        assert len(updated_server.cached_tools) == len(tools)
        assert updated_server.last_sync_at is not None
        print(f"✅ Кэш обновлен: {len(updated_server.cached_tools)} тулов")
        
        print("\n✅ Полный workflow успешно выполнен!")
    
    finally:
        await mcp_repo.delete("github_copilot_workflow_test")
        
        if 'tools' in locals():
            for tool in tools:
                await tool_repo.delete(tool.tool_id)
        
        print("\n🧹 Очистка завершена")


@pytest.mark.asyncio
async def test_github_copilot_with_mock_llm(test_company, mcp_repo, agent_repo, tool_repo, agent_factory):
    """
    End-to-end тест: агент + GitHub Copilot MCP + мок LLM.
    
    Проверяем полную интеграцию с мокированным LLM.
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models import AgentConfig
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    from unittest.mock import MagicMock, AsyncMock
    import uuid
    import os
    
    api_key = os.getenv("GITHUB_COPILOT_TOKEN")
    if not api_key:
        pytest.skip("GITHUB_COPILOT_TOKEN not set")
    
    server_config = MCPServerConfig(
        server_id="github_copilot",
        company_id=test_company.company_id,
        name="GitHub Copilot",
        url="https://api.githubcopilot.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {api_key}"},
        is_active=True
    )
    
    await mcp_repo.set(server_config)
    
    try:
        print("\n" + "="*70)
        print("1️⃣ Синхронизация GitHub Copilot MCP тулов")
        print("="*70)
        
        mcp_tools = await sync_mcp_server_tools("github_copilot", test_company.company_id)
        print(f"✅ Синхронизировано {len(mcp_tools)} MCP тулов")
        
        if len(mcp_tools) == 0:
            print("⚠️  Нет доступных тулов от GitHub Copilot MCP")
            return
        
        first_tool_name = mcp_tools[0].params.get("tool_name", "unknown_tool")
        
        print("\n" + "="*70)
        print("2️⃣ Создание агента с GitHub Copilot MCP тулами")
        print("="*70)
        
        agent_config = AgentConfig(
            agent_id="copilot_test_agent",
            name="Copilot Test Agent",
            description="Агент для тестирования GitHub Copilot",
            prompt="""
Ты помощник-разработчик с доступом к GitHub Copilot.
Используй доступные тулы для помощи с кодом.
""",
            tools=mcp_tools
        )
        
        await agent_repo.set(agent_config)
        print(f"✅ Агент создан с {len(mcp_tools)} MCP тулами")
        
        print("\n" + "="*70)
        print("3️⃣ Загрузка агента через AgentFactory")
        print("="*70)
        
        agent = await agent_factory.get_agent("copilot_test_agent")
        
        loaded_tools = await agent.get_tools()
        print(f"✅ Агент загружен с {len(loaded_tools)} тулами")
        
        print("\n" + "="*70)
        print("4️⃣ Мокирование LLM для вызова GitHub Copilot тула")
        print("="*70)
        
        call_count = [0]
        
        async def mock_ainvoke(messages, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                safe_tool_name = first_tool_name.replace("-", "_")
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": safe_tool_name,
                        "args": {"query": "test"},
                        "id": "call_test_1",
                        "type": "tool_call"
                    }]
                )
            else:
                return AIMessage(content="GitHub Copilot тул выполнен успешно!")
        
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=mock_ainvoke)
        
        agent.llm = mock_llm
        print(f"✅ LLM настроен на вызов первого тула: {first_tool_name}")
        
        print("\n" + "="*70)
        print("5️⃣ Выполнение агента")
        print("="*70)
        
        compiled_graph = await agent.compile_graph()
        
        session_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {"messages": [HumanMessage(content="Помоги с кодом")]},
            config={"configurable": {"session_id": session_id}}
        )
        
        print("✅ Агент выполнен")
        
        print("\n" + "="*70)
        print("6️⃣ Проверка результата")
        print("="*70)
        
        messages = result.get("messages", [])
        print(f"   Всего сообщений: {len(messages)}")
        
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        print(f"   Tool messages: {len(tool_messages)}")
        
        if tool_messages:
            print("\n   📦 ToolMessage от GitHub Copilot:")
            first_tool_message = tool_messages[0]
            print(f"      Tool call ID: {first_tool_message.tool_call_id}")
            print(f"      Content preview: {first_tool_message.content[:200]}...")
            
            assert len(first_tool_message.content) > 0
            assert isinstance(first_tool_message.content, str)
        
        print("\n" + "="*70)
        print("✅ END-TO-END ТЕСТ С GITHUB COPILOT УСПЕШНО ПРОЙДЕН!")
        print("="*70)
    
    finally:
        await agent_repo.delete("copilot_test_agent")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await tool_repo.delete(tool.tool_id)
        await mcp_repo.delete("github_copilot")

"""
End-to-end тест: AgentFactory + MCP тулы + мок LLM.

Проверяем что агент может использовать MCP тулы через мокированный LLM.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, ToolCall


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_weather_agent_with_context7_mcp_tools(setup_mcp_servers, test_company, agent_repo, tool_repo, agent_factory):
    """
    End-to-end тест: WeatherAgent + Context7 MCP тулы.
    
    Workflow:
    1. Синхронизируем Context7 тулы
    2. Добавляем их в WeatherAgent
    3. Мокаем LLM чтобы он вызвал MCP тул
    4. Проверяем что тул выполнился успешно
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models import AgentConfig
    from apps.agents.tools.misc.standard import ask_user
    
    try:
        print("\n" + "="*70)
        print("📝 Шаг 1: Синхронизация Context7 MCP тулов")
        print("="*70)
        
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        print(f"✅ Синхронизировано {len(mcp_tools)} MCP тулов:")
        for tool in mcp_tools:
            print(f"   - {tool.tool_id}")
        
        print("\n" + "="*70)
        print("🤖 Шаг 2: Создаем агента с MCP тулами")
        print("="*70)
        
        agent_config = AgentConfig(
            agent_id="weather_with_mcp",
            name="Weather Agent with MCP",
            description="Погодный агент с доступом к документации через Context7",
            prompt="""
Ты погодный помощник с доступом к документации.

ИНСТРУМЕНТЫ:
- resolve_library_id: поиск библиотек в документации
- get_library_docs: получение документации библиотек

Если пользователь спрашивает про библиотеку или документацию:
1. Используй resolve_library_id для поиска
2. Затем get_library_docs для получения документации
""",
            tools=[
                ask_user,
                *mcp_tools,
            ]
        )
        
        await agent_repo.set(agent_config)
        print(f"✅ Агент создан с {len(mcp_tools)} MCP тулами")
        
        print("\n" + "="*70)
        print("🏭 Шаг 3: Загружаем агента через AgentFactory")
        print("="*70)
        
        saved_config = await agent_repo.get("weather_with_mcp")
        print("   Конфиг из БД:")
        print(f"   - agent_id: {saved_config.agent_id}")
        print(f"   - tools в конфиге: {len(saved_config.tools)}")
        for t in saved_config.tools:
            print(f"      • {t.tool_id} (code_mode: {t.code_mode})")
        
        import logging
        logging.getLogger('app.core.agent_factory').setLevel(logging.DEBUG)
        logging.getLogger('app.core.tool_factory').setLevel(logging.DEBUG)
        
        agent = await agent_factory.get_agent("weather_with_mcp")
        
        print("\n✅ Агент загружен")
        print(f"   Тип агента: {type(agent).__name__}")
        
        loaded_tools = await agent.get_tools()
        print(f"   Всего тулов через get_tools(): {len(loaded_tools)}")
        
        mcp_tool_names = []
        for tool in loaded_tools:
            tool_name = getattr(tool, 'name', 'unknown')
            print(f"   - {tool_name}")
            if 'resolve' in tool_name or 'library' in tool_name:
                mcp_tool_names.append(tool_name)
        
        assert len(mcp_tool_names) >= 1, f"Должен быть хотя бы один MCP тул. Всего тулов: {len(loaded_tools)}"
        print(f"\n✅ Найдено {len(mcp_tool_names)} MCP тулов: {mcp_tool_names}")
        
        print("\n" + "="*70)
        print("🎭 Шаг 4: Мокаем LLM для вызова MCP тула")
        print("="*70)
        
        mock_llm_response = AIMessage(
            content="",
            tool_calls=[
                ToolCall(
                    name="resolve_library_id",
                    args={"libraryName": "fastapi"},
                    id="call_1",
                    type="tool_call"
                )
            ]
        )
        
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
        
        agent.llm = mock_llm
        
        print("✅ LLM замокан для вызова resolve_library_id('fastapi')")
        
        print("\n" + "="*70)
        print("🚀 Шаг 5: Вызываем агента")
        print("="*70)
        
        compiled_graph = await agent.compile_graph()
        
        from langchain_core.messages import HumanMessage
        import uuid
        
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {"messages": [HumanMessage(content="Найди документацию FastAPI")]},
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print("✅ Агент выполнен")
        
        assert "messages" in result
        assert len(result["messages"]) > 0
        
        print("\n📋 Результат выполнения:")
        print(f"   Всего сообщений: {len(result['messages'])}")
        
        from langchain_core.messages import ToolMessage
        
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        print(f"   Tool messages: {len(tool_messages)}")
        
        if tool_messages:
            print("\n   📦 Первый ToolMessage:")
            first_tool_msg = tool_messages[0]
            print(f"      Content: {first_tool_msg.content[:300]}...")
            
            assert len(first_tool_msg.content) > 0
            assert isinstance(first_tool_msg.content, str)
        
        print("\n" + "="*70)
        print("✅ End-to-end тест успешно пройден!")
        print("="*70)
    
    finally:
        await agent_repo.delete("weather_with_mcp")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await tool_repo.delete(tool.tool_id)


@pytest.mark.asyncio
async def test_agent_calls_mcp_tool_directly(test_company, mcp_repo, tool_repo, tool_factory):
    """
    Прямой тест вызова MCP тула через ToolFactory.
    
    Без агента - просто вызываем MCP тул напрямую.
    """
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    import os
    
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    server_config = MCPServerConfig(
        server_id="context7",
        company_id=test_company.company_id,
        name="Context7",
        url="https://mcp.context7.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {api_key}"},
        is_active=True
    )
    
    await mcp_repo.set(server_config)
    
    try:
        print("\n📝 Синхронизируем Context7 тулы")
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        resolve_tool_ref = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        assert resolve_tool_ref is not None
        
        print(f"✅ Найден тул: {resolve_tool_ref.tool_id}")
        
        print("\n🔧 Создаем LangChain тул через ToolFactory")
        langchain_tool = await tool_factory._create_mcp_tool(resolve_tool_ref)
        
        print(f"✅ Тул создан: {langchain_tool.name}")
        
        print("\n🚀 Вызываем MCP тул напрямую")
        result = await langchain_tool.ainvoke({"libraryName": "langchain"})
        
        print("✅ Тул выполнен")
        print("\n📋 Результат:")
        print(f"   {result[:500]}...")
        
        assert result is not None
        assert len(result) > 0
        assert "langchain" in result.lower() or "library" in result.lower()
        
        print("\n✅ MCP тул работает корректно!")
    
    finally:
        await mcp_repo.delete("context7")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await tool_repo.delete(tool.tool_id)


@pytest.mark.asyncio
async def test_weather_agent_with_mcp_real_execution(setup_mcp_servers, test_company, agent_repo, tool_repo, agent_factory):
    """
    Реальное выполнение WeatherAgent с MCP тулом (с мок LLM).
    
    Проверяем полную интеграцию:
    - Синхронизация MCP
    - Создание агента
    - Вызов через AgentFactory
    - Мок LLM вызывает MCP тул
    - Результат возвращается пользователю
    """
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models import AgentConfig
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    
    try:
        print("\n1️⃣ Синхронизация Context7 MCP тулов...")
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        resolve_tool = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        print(f"   ✅ MCP тул: {resolve_tool.tool_id}")
        
        print("\n2️⃣ Создание агента с MCP тулами...")
        agent_config = AgentConfig(
            agent_id="weather_mcp_test",
            name="Weather MCP Test",
            prompt="Ты помощник с доступом к документации",
            tools=mcp_tools
        )
        await agent_repo.set(agent_config)
        
        print("\n3️⃣ Загрузка агента через AgentFactory...")
        agent = await agent_factory.get_agent("weather_mcp_test")
        print(f"   ✅ Агент загружен с {len(agent.tools)} тулами")
        
        print("\n4️⃣ Мокирование LLM для вызова MCP тула...")
        
        call_count = [0]
        
        async def mock_ainvoke(messages, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "resolve_library_id",
                            "args": {"libraryName": "fastapi"},
                            "id": "call_resolve_1",
                            "type": "tool_call"
                        }
                    ]
                )
            else:
                return AIMessage(
                    content="Нашел информацию о FastAPI через Context7 MCP!"
                )
        
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=mock_ainvoke)
        
        agent.llm = mock_llm
        print("   ✅ LLM настроен на вызов resolve_library_id")
        
        print("\n5️⃣ Выполнение агента...")
        compiled_graph = await agent.compile_graph()
        
        import uuid
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {"messages": [HumanMessage(content="Найди документацию FastAPI")]},
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print("   ✅ Агент выполнен")
        
        print("\n6️⃣ Проверка результата...")
        
        messages = result.get("messages", [])
        print(f"   Всего сообщений: {len(messages)}")
        
        assert len(messages) >= 3
        
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1, "Должен быть ToolMessage от MCP тула"
        
        first_tool_message = tool_messages[0]
        print("\n   📦 ToolMessage от MCP тула:")
        print(f"      Tool call ID: {first_tool_message.tool_call_id}")
        print(f"      Content preview: {first_tool_message.content[:200]}...")
        
        assert len(first_tool_message.content) > 0
        assert isinstance(first_tool_message.content, str)
        
        content_lower = first_tool_message.content.lower()
        assert "library" in content_lower or "available" in content_lower or "fastapi" in content_lower
        
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        final_message = ai_messages[-1] if ai_messages else None
        
        if final_message:
            print("\n   💬 Финальный ответ агента:")
            print(f"      {final_message.content}")
            assert "FastAPI" in final_message.content or "Context7" in final_message.content
        
        print("\n" + "="*70)
        print("✅ END-TO-END ТЕСТ УСПЕШНО ПРОЙДЕН!")
        print("="*70)
        print("\n📊 Резюме:")
        print(f"   - MCP тулов синхронизировано: {len(mcp_tools)}")
        print(f"   - Агент загружен с тулами: {len(agent.tools)}")
        print(f"   - LLM вызовов: {call_count[0]}")
        print(f"   - Сообщений в результате: {len(messages)}")
        print(f"   - ToolMessages (MCP вызовы): {len(tool_messages)}")
        print("   - MCP тул реально выполнился: ✅")
    
    finally:
        await agent_repo.delete("weather_mcp_test")
        for tool in mcp_tools:
            await tool_repo.delete(tool.tool_id)


@pytest.mark.asyncio
async def test_agent_with_multiple_mcp_tools(test_company, mcp_repo, agent_repo, tool_repo, agent_factory):
    """
    Тест агента с несколькими MCP тулами в одном запросе.
    
    LLM последовательно вызывает:
    1. resolve-library-id
    2. get-library-docs
    """
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    from apps.agents.services.mcp_sync import sync_mcp_server_tools
    from apps.agents.models import AgentConfig
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    import os
    
    api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")
    
    server_config = MCPServerConfig(
        server_id="context7",
        company_id=test_company.company_id,
        name="Context7",
        url="https://mcp.context7.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {api_key}"},
        is_active=True
    )
    
    await mcp_repo.set(server_config)
    
    try:
        print("\n📝 Подготовка: синхронизация и создание агента...")
        
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        agent_config = AgentConfig(
            agent_id="multi_mcp_test",
            name="Multi MCP Test",
            prompt="Используй оба MCP тула последовательно",
            tools=mcp_tools
        )
        await agent_repo.set(agent_config)
        
        agent = await agent_factory.get_agent("multi_mcp_test")
        
        print(f"✅ Агент создан с {len(agent.tools)} тулами")
        
        call_count = [0]
        
        async def mock_sequential_calls(messages, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "resolve_library_id",
                        "args": {"libraryName": "langchain"},
                        "id": "call_1",
                        "type": "tool_call"
                    }]
                )
            elif call_count[0] == 2:
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_library_docs",
                        "args": {
                            "context7CompatibleLibraryID": "/langchain-ai/langchain",
                            "topic": "agents"
                        },
                        "id": "call_2",
                        "type": "tool_call"
                    }]
                )
            else:
                return AIMessage(content="Документация получена через оба MCP тула!")
        
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=mock_sequential_calls)
        
        agent.llm = mock_llm
        
        print("\n🚀 Выполняем агента с последовательными вызовами MCP тулов...")
        compiled_graph = await agent.compile_graph()
        
        import uuid
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {"messages": [HumanMessage(content="Найди и покажи документацию LangChain")]},
            config={"configurable": {"thread_id": thread_id}}
        )
        
        messages = result.get("messages", [])
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        
        print("\n✅ Результат:")
        print(f"   LLM вызовов: {call_count[0]}")
        print(f"   Tool messages: {len(tool_messages)}")
        
        assert len(tool_messages) >= 2, "Должно быть 2 ToolMessage от двух MCP тулов"
        
        print(f"\n   📦 ToolMessage 1: {tool_messages[0].content[:150]}...")
        print(f"   📦 ToolMessage 2: {tool_messages[1].content[:150]}...")
        
        print("\n✅ Оба MCP тула успешно выполнены!")
    
    finally:
        await agent_repo.delete("multi_mcp_test")
        for tool in mcp_tools:
            await tool_repo.delete(tool.tool_id)

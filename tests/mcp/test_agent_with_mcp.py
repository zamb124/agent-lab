"""
from app.core.container import get_container
End-to-end тест: AgentFactory + MCP тулы + мок LLM.

Проверяем что агент может использовать MCP тулы через мокированный LLM.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, ToolCall


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_weather_agent_with_context7_mcp_tools(setup_mcp_servers, test_company):
    """
    End-to-end тест: WeatherAgent + Context7 MCP тулы.
    
    Workflow:
    1. Синхронизируем Context7 тулы
    2. Добавляем их в WeatherAgent
    3. Мокаем LLM чтобы он вызвал MCP тул
    4. Проверяем что тул выполнился успешно
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig
    from app.db.repositories.agent_repository import AgentRepository
    from app.db.repositories.storage import Storage
    from app.tools.misc.standard import ask_user
    
    storage = Storage()
    agent_repo = AgentRepository(storage)
    
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
        
        # Создаем WeatherAgent с MCP тулами
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
                *mcp_tools,  # Добавляем MCP тулы
            ]
        )
        
        await agent_repo.set(agent_config)
        print(f"✅ Агент создан с {len(mcp_tools)} MCP тулами")
        
        print("\n" + "="*70)
        print("🏭 Шаг 3: Загружаем агента через AgentFactory")
        print("="*70)
        
        # Проверяем что конфиг сохранился
        saved_config = await agent_repo.get("weather_with_mcp")
        print(f"   Конфиг из БД:")
        print(f"   - agent_id: {saved_config.agent_id}")
        print(f"   - tools в конфиге: {len(saved_config.tools)}")
        for t in saved_config.tools:
            print(f"      • {t.tool_id} (code_mode: {t.code_mode})")
        
        agent_factory = get_container().agent_factory
        
        # Включаем DEBUG логирование для отладки
        import logging
        logging.getLogger('app.core.agent_factory').setLevel(logging.DEBUG)
        logging.getLogger('app.core.tool_factory').setLevel(logging.DEBUG)
        
        agent = await agent_factory.get_agent("weather_with_mcp")
        
        print(f"\n✅ Агент загружен")
        print(f"   Тип агента: {type(agent).__name__}")
        
        # Получаем тулы через метод get_tools (асинхронный!)
        loaded_tools = await agent.get_tools()
        print(f"   Всего тулов через get_tools(): {len(loaded_tools)}")
        
        # Проверяем что MCP тулы загружены
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
        
        # Создаем мок LLM который вызовет MCP тул
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
        
        # Мокаем метод bind_tools и invoke у LLM
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
        
        # Подменяем LLM в агенте
        agent.llm = mock_llm
        
        print("✅ LLM замокан для вызова resolve_library_id('fastapi')")
        
        print("\n" + "="*70)
        print("🚀 Шаг 5: Вызываем агента")
        print("="*70)
        
        # Компилируем граф (обязательно для ReActAgent)
        compiled_graph = await agent.compile_graph()
        
        # Вызываем агента с thread_id для checkpointer
        from langchain_core.messages import HumanMessage
        import uuid
        
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {"messages": [HumanMessage(content="Найди документацию FastAPI")]},
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print("✅ Агент выполнен")
        
        # Проверяем что в результате есть сообщения
        assert "messages" in result
        assert len(result["messages"]) > 0
        
        print(f"\n📋 Результат выполнения:")
        print(f"   Всего сообщений: {len(result['messages'])}")
        
        # Проверяем что есть ToolMessage (результат выполнения тула)
        from langchain_core.messages import ToolMessage
        
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        print(f"   Tool messages: {len(tool_messages)}")
        
        if tool_messages:
            print(f"\n   📦 Первый ToolMessage:")
            first_tool_msg = tool_messages[0]
            print(f"      Content: {first_tool_msg.content[:300]}...")
            
            # Проверяем что в ответе есть что-то от Context7
            assert len(first_tool_msg.content) > 0
            assert isinstance(first_tool_msg.content, str)
        
        print("\n" + "="*70)
        print("✅ End-to-end тест успешно пройден!")
        print("="*70)
    
    finally:
        # Очистка
        await agent_repo.delete("weather_with_mcp")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await storage.delete(f"tool:{tool.tool_id}")


@pytest.mark.asyncio
async def test_agent_calls_mcp_tool_directly(test_company):
    """
    Прямой тест вызова MCP тула через ToolFactory.
    
    Без агента - просто вызываем MCP тул напрямую.
    """
    from app.models.mcp_models import MCPServerConfig, MCPTransportType
    from app.db.repositories.mcp_repository import MCPServerRepository
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.tool_factory import ToolFactory
    from app.db.repositories.storage import Storage
    import os
    
    storage = Storage()
    mcp_repo = MCPServerRepository(storage)
    tool_factory = ToolFactory()
    
    # Создаем MCP сервер
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
        
        # Берем resolve-library-id тул
        resolve_tool_ref = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        assert resolve_tool_ref is not None
        
        print(f"✅ Найден тул: {resolve_tool_ref.tool_id}")
        
        print("\n🔧 Создаем LangChain тул через ToolFactory")
        langchain_tool = await tool_factory._create_mcp_tool(resolve_tool_ref)
        
        print(f"✅ Тул создан: {langchain_tool.name}")
        
        print("\n🚀 Вызываем MCP тул напрямую")
        result = await langchain_tool.ainvoke({"libraryName": "langchain"})
        
        print(f"✅ Тул выполнен")
        print(f"\n📋 Результат:")
        print(f"   {result[:500]}...")
        
        # Проверки
        assert result is not None
        assert len(result) > 0
        assert "langchain" in result.lower() or "library" in result.lower()
        
        print(f"\n✅ MCP тул работает корректно!")
    
    finally:
        # Очистка
        await mcp_repo.delete("context7", test_company.company_id)
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await storage.delete(f"tool:{tool.tool_id}")


@pytest.mark.asyncio
async def test_weather_agent_with_mcp_real_execution(setup_mcp_servers, test_company):
    """
    Реальное выполнение WeatherAgent с MCP тулом (с мок LLM).
    
    Проверяем полную интеграцию:
    - Синхронизация MCP
    - Создание агента
    - Вызов через AgentFactory
    - Мок LLM вызывает MCP тул
    - Результат возвращается пользователю
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig
    from app.db.repositories.agent_repository import AgentRepository
    from app.db.repositories.storage import Storage
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    
    storage = Storage()
    agent_repo = AgentRepository(storage)
    
    try:
        # 1. Синхронизируем MCP тулы
        print("\n1️⃣ Синхронизация Context7 MCP тулов...")
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        resolve_tool = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        print(f"   ✅ MCP тул: {resolve_tool.tool_id}")
        
        # 2. Создаем агента
        print("\n2️⃣ Создание агента с MCP тулами...")
        agent_config = AgentConfig(
            agent_id="weather_mcp_test",
            name="Weather MCP Test",
            prompt="Ты помощник с доступом к документации",
            tools=mcp_tools
        )
        await agent_repo.set(agent_config)
        
        # 3. Загружаем через фабрику
        print("\n3️⃣ Загрузка агента через AgentFactory...")
        agent_factory = get_container().agent_factory
        agent = await agent_factory.get_agent("weather_mcp_test")
        print(f"   ✅ Агент загружен с {len(agent.tools)} тулами")
        
        # 4. Создаем мок LLM который последовательно:
        #    - Сначала вызовет MCP тул
        #    - Потом даст финальный ответ
        print("\n4️⃣ Мокирование LLM для вызова MCP тула...")
        
        call_count = [0]
        
        async def mock_ainvoke(messages, **kwargs):
            """Мок LLM который вызывает MCP тул на первом вызове"""
            call_count[0] += 1
            
            if call_count[0] == 1:
                # Первый вызов - вызываем MCP тул
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
                # Второй вызов - даем финальный ответ
                return AIMessage(
                    content="Нашел информацию о FastAPI через Context7 MCP!"
                )
        
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=mock_ainvoke)
        
        agent.llm = mock_llm
        print("   ✅ LLM настроен на вызов resolve_library_id")
        
        # 5. Вызываем агента
        print("\n5️⃣ Выполнение агента...")
        compiled_graph = await agent.compile_graph()
        
        import uuid
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {"messages": [HumanMessage(content="Найди документацию FastAPI")]},
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print("   ✅ Агент выполнен")
        
        # 6. Проверяем результат
        print("\n6️⃣ Проверка результата...")
        
        messages = result.get("messages", [])
        print(f"   Всего сообщений: {len(messages)}")
        
        # Должны быть: HumanMessage, AIMessage (с tool_call), ToolMessage, AIMessage (финальный)
        assert len(messages) >= 3
        
        # Проверяем ToolMessage
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1, "Должен быть ToolMessage от MCP тула"
        
        first_tool_message = tool_messages[0]
        print(f"\n   📦 ToolMessage от MCP тула:")
        print(f"      Tool call ID: {first_tool_message.tool_call_id}")
        print(f"      Content preview: {first_tool_message.content[:200]}...")
        
        # Проверяем что это реальный ответ от Context7
        assert len(first_tool_message.content) > 0
        assert isinstance(first_tool_message.content, str)
        
        # В ответе Context7 обычно есть "Library" или "Available"
        content_lower = first_tool_message.content.lower()
        assert "library" in content_lower or "available" in content_lower or "fastapi" in content_lower
        
        # Проверяем финальный ответ
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        final_message = ai_messages[-1] if ai_messages else None
        
        if final_message:
            print(f"\n   💬 Финальный ответ агента:")
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
        # Очистка
        await agent_repo.delete("weather_mcp_test")
        for tool in mcp_tools:
            await storage.delete(f"tool:{tool.tool_id}")


@pytest.mark.asyncio
async def test_agent_with_multiple_mcp_tools(test_company):
    """
    Тест агента с несколькими MCP тулами в одном запросе.
    
    LLM последовательно вызывает:
    1. resolve-library-id
    2. get-library-docs
    """
    from app.models.mcp_models import MCPServerConfig, MCPTransportType
    from app.db.repositories.mcp_repository import MCPServerRepository
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig
    from app.db.repositories.agent_repository import AgentRepository
    from app.db.repositories.storage import Storage
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    import os
    
    storage = Storage()
    agent_repo = AgentRepository(storage)
    mcp_repo = MCPServerRepository(storage)
    
    # Создаем MCP сервер
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
        
        agent_factory = get_container().agent_factory
        agent = await agent_factory.get_agent("multi_mcp_test")
        
        print(f"✅ Агент создан с {len(agent.tools)} тулами")
        
        # Мокаем LLM для последовательного вызова двух тулов
        call_count = [0]
        
        async def mock_sequential_calls(messages, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # Вызов 1: resolve-library-id
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
                # Вызов 2: get-library-docs
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
                # Финальный ответ
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
        
        print(f"\n✅ Результат:")
        print(f"   LLM вызовов: {call_count[0]}")
        print(f"   Tool messages: {len(tool_messages)}")
        
        # Должно быть 2 ToolMessage (от двух MCP тулов)
        assert len(tool_messages) >= 2, "Должно быть 2 ToolMessage от двух MCP тулов"
        
        print(f"\n   📦 ToolMessage 1: {tool_messages[0].content[:150]}...")
        print(f"   📦 ToolMessage 2: {tool_messages[1].content[:150]}...")
        
        print(f"\n✅ Оба MCP тула успешно выполнены!")
    
    finally:
        # Очистка
        await agent_repo.delete("multi_mcp_test")
        for tool in mcp_tools:
            await storage.delete(f"tool:{tool.tool_id}")


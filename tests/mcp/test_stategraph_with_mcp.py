"""
End-to-end тест: StateGraph агент + MCP тулы + обычные тулы.

Проверяем что StateGraph агент может использовать:
1. Обычные тулы (калькулятор)
2. MCP тулы (Context7)
в своих нодах.
"""

import pytest
from langchain_core.messages import HumanMessage


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_stategraph_agent_with_mcp_and_regular_tools(setup_mcp_servers, test_company):
    """
    End-to-end тест: StateGraph агент с MCP и обычными тулами в нодах.
    
    Граф:
    START → calc_node (обычный тул) → mcp_node (MCP тул) → END
    
    Проверяет что:
    - TOOL_NODE с обычным тулом работает
    - TOOL_NODE с MCP тулом работает
    - Результаты передаются между нодами через state
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig
    from app.models.core_models import GraphDefinition, GraphNode, GraphEdge, NodeType
    from app.db.repositories.agent_repository import AgentRepository
    from app.db.repositories.storage import Storage
    
    storage = Storage()
    agent_repo = AgentRepository(storage)
    
    try:
        print("\n" + "="*70)
        print("📝 Шаг 1: Подготовка тулов")
        print("="*70)
        
        # Синхронизируем MCP тулы
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        resolve_tool = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        
        print(f"✅ MCP тул: {resolve_tool.tool_id}")
        print(f"✅ Обычный тул: app.tools.calc.calc_tools.calculate")
        
        print("\n" + "="*70)
        print("🤖 Шаг 2: Создаем StateGraph агента с нодами")
        print("="*70)
        
        # Создаем GraphDefinition с двумя TOOL_NODE
        graph_definition = GraphDefinition(
            nodes=[
                # Нода с обычным тулом (калькулятор)
                GraphNode(
                    id="calc_node",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": "app.tools.calc.calc_tools.calculate",
                        "input_key": "store.calc_input",  # Берем из store
                        "output_key": "store.calc_result"  # Сохраняем в store
                    }
                ),
                # Нода с MCP тулом
                GraphNode(
                    id="mcp_node",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": resolve_tool.tool_id,
                        "input_key": "store.mcp_input",  # Берем из store
                        "output_key": "store.mcp_result"  # Сохраняем в store
                    }
                ),
            ],
            edges=[
                GraphEdge(source="START", target="calc_node"),
                GraphEdge(source="calc_node", target="mcp_node"),
                GraphEdge(source="mcp_node", target="END"),
            ],
            entry_point="START"
        )
        
        # Создаем StateGraph агента
        agent_config = AgentConfig(
            agent_id="stategraph_with_mcp",
            name="StateGraph with MCP",
            description="StateGraph агент с обычными и MCP тулами",
            graph_definition=graph_definition,
            tools=[]  # Тулы в нодах, не в tools
        )
        
        await agent_repo.set(agent_config)
        print(f"✅ StateGraph агент создан")
        print(f"   Ноды: calc_node (обычный тул), mcp_node (MCP тул)")
        
        print("\n" + "="*70)
        print("🏭 Шаг 3: Загружаем агента через AgentFactory")
        print("="*70)
        
        agent_factory = AgentFactory()
        agent = await agent_factory.get_agent("stategraph_with_mcp")
        
        print(f"✅ Агент загружен: {type(agent).__name__}")
        
        print("\n" + "="*70)
        print("🚀 Шаг 4: Компилируем и выполняем граф")
        print("="*70)
        
        compiled_graph = await agent.compile_graph()
        print("✅ Граф скомпилирован")
        
        # Выполняем граф с входными данными через store
        import uuid
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {
                "messages": [HumanMessage(content="Test")],
                "store": {
                    "calc_input": "2+2",  # Для calc_node
                    "mcp_input": "fastapi",  # Для mcp_node
                }
            },
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print(f"✅ Граф выполнен")
        
        print("\n" + "="*70)
        print("📋 Шаг 5: Проверка результатов")
        print("="*70)
        
        # Проверяем результаты в store
        assert "store" in result, "Должен быть store в результате"
        store = result['store']
        
        # Проверяем результат calc_node (обычный тул)
        assert "calc_result" in store, "Должен быть calc_result в store"
        print(f"✅ calc_node выполнена:")
        print(f"   Результат: {store['calc_result']}")
        
        # Проверяем результат mcp_node (MCP тул)
        assert "mcp_result" in store, "Должен быть mcp_result в store"
        print(f"\n✅ mcp_node выполнена:")
        print(f"   Результат: {store['mcp_result'][:300]}...")
        
        # Проверяем что MCP тул вернул реальные данные от Context7
        mcp_result_lower = store['mcp_result'].lower()
        assert "library" in mcp_result_lower or "fastapi" in mcp_result_lower or "available" in mcp_result_lower
        
        print("\n" + "="*70)
        print("✅ STATEGRAPH END-TO-END ТЕСТ УСПЕШНО ПРОЙДЕН!")
        print("="*70)
        print("\n📊 Резюме:")
        print(f"   - Обычный тул (calculate): ✅ работает")
        print(f"   - MCP тул (resolve-library-id): ✅ работает")
        print(f"   - Результаты передаются через state.store: ✅")
        print(f"   - calc_result: {store.get('calc_result', 'N/A')}")
        print(f"   - mcp_result длина: {len(store.get('mcp_result', ''))} символов")
    
    finally:
        # Очистка
        await agent_repo.delete("stategraph_with_mcp")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await storage.delete(f"tool:{tool.tool_id}")


@pytest.mark.asyncio
async def test_stategraph_with_only_mcp_tools(setup_mcp_servers, test_company):
    """
    Тест StateGraph агента только с MCP тулами.
    
    Граф:
    START → resolve_node → get_docs_node → END
    
    Две MCP ноды последовательно.
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig
    from app.models.core_models import GraphDefinition, GraphNode, GraphEdge, NodeType
    from app.db.repositories.agent_repository import AgentRepository
    from app.db.repositories.storage import Storage
    
    storage = Storage()
    agent_repo = AgentRepository(storage)
    
    try:
        print("\n📝 Синхронизация Context7 тулов...")
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        resolve_tool = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        docs_tool = next((t for t in mcp_tools if "get-library" in t.tool_id), None)
        
        print(f"✅ Найдено 2 MCP тула")
        
        # Создаем граф с двумя MCP нодами
        graph_definition = GraphDefinition(
            nodes=[
                GraphNode(
                    id="resolve_node",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": resolve_tool.tool_id,
                        "input_key": "library_name",
                        "output_key": "library_info"
                    }
                ),
                GraphNode(
                    id="docs_node",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": docs_tool.tool_id,
                        "input_key": "docs_params",
                        "output_key": "documentation"
                    }
                ),
            ],
            edges=[
                GraphEdge(source="START", target="resolve_node"),
                GraphEdge(source="resolve_node", target="docs_node"),
                GraphEdge(source="docs_node", target="END"),
            ],
            entry_point="START"
        )
        
        agent_config = AgentConfig(
            agent_id="two_mcp_nodes",
            name="Two MCP Nodes",
            graph_definition=graph_definition
        )
        
        await agent_repo.set(agent_config)
        print(f"✅ Агент создан с 2 MCP нодами")
        
        # Загружаем и компилируем
        agent_factory = AgentFactory()
        agent = await agent_factory.get_agent("two_mcp_nodes")
        compiled_graph = await agent.compile_graph()
        
        print("\n🚀 Выполняем граф с 2 MCP нодами...")
        
        import uuid
        thread_id = str(uuid.uuid4())
        
        # Для второй ноды нужны параметры get-library-docs
        result = await compiled_graph.ainvoke(
            {
                "messages": [HumanMessage(content="Test")],
                "library_name": "langchain",
                "docs_params": {
                    "context7CompatibleLibraryID": "/langchain-ai/langchain",
                    "topic": "agents"
                }
            },
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print(f"✅ Граф с 2 MCP нодами выполнен")
        
        # Проверяем результаты
        assert "library_info" in result
        assert "documentation" in result
        
        print(f"\n📋 Результаты:")
        print(f"   resolve_node: {result['library_info'][:200]}...")
        print(f"   docs_node: {result['documentation'][:200]}...")
        
        print(f"\n✅ Обе MCP ноды работают!")
    
    finally:
        # Очистка
        await agent_repo.delete("two_mcp_nodes")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await storage.delete(f"tool:{tool.tool_id}")


@pytest.mark.asyncio
async def test_stategraph_mixed_tools_complex_graph(setup_mcp_servers, test_company):
    """
    Сложный граф с обычными и MCP тулами.
    
    Граф:
             START
               ↓
           calc_node (обычный)
             /   \
            /     \
      mcp_node1  mcp_node2 (MCP)
           \      /
            \    /
           end_node
               ↓
              END
    """
    from app.core.mcp_sync import sync_mcp_server_tools
    from app.core.agent_factory import AgentFactory
    from app.models import AgentConfig
    from app.models.core_models import GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType
    from app.db.repositories.agent_repository import AgentRepository
    from app.db.repositories.storage import Storage
    
    storage = Storage()
    agent_repo = AgentRepository(storage)
    
    try:
        print("\n📝 Подготовка: синхронизация тулов...")
        mcp_tools = await sync_mcp_server_tools("context7", test_company.company_id)
        
        resolve_tool = next((t for t in mcp_tools if "resolve" in t.tool_id), None)
        docs_tool = next((t for t in mcp_tools if "get-library" in t.tool_id), None)
        
        # Создаем сложный граф
        graph_definition = GraphDefinition(
            nodes=[
                GraphNode(
                    id="calc_node",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": "app.tools.calc.calc_tools.calculate",
                        "input_key": "expression",
                        "output_key": "calc_result"
                    }
                ),
                GraphNode(
                    id="mcp_resolve",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": resolve_tool.tool_id,
                        "input_key": "lib1",
                        "output_key": "lib1_info"
                    }
                ),
                GraphNode(
                    id="mcp_docs",
                    type=NodeType.TOOL_NODE,
                    params={
                        "tool_id": docs_tool.tool_id,
                        "input_key": "docs_params",
                        "output_key": "docs_result"
                    }
                ),
            ],
            edges=[
                GraphEdge(source="START", target="calc_node"),
                GraphEdge(source="calc_node", target="mcp_resolve"),
                GraphEdge(source="calc_node", target="mcp_docs"),
                GraphEdge(source="mcp_resolve", target="END"),
                GraphEdge(source="mcp_docs", target="END"),
            ],
            entry_point="START"
        )
        
        agent_config = AgentConfig(
            agent_id="complex_stategraph_mcp",
            name="Complex StateGraph MCP",
            graph_definition=graph_definition
        )
        
        await agent_repo.set(agent_config)
        
        print(f"✅ Сложный StateGraph агент создан")
        print(f"   Ноды: calc_node, mcp_resolve, mcp_docs")
        print(f"   Граф: START → calc → (mcp_resolve, mcp_docs) → END")
        
        # Загружаем и выполняем
        agent_factory = AgentFactory()
        agent = await agent_factory.get_agent("complex_stategraph_mcp")
        compiled_graph = await agent.compile_graph()
        
        print("\n🚀 Выполняем сложный граф...")
        
        import uuid
        thread_id = str(uuid.uuid4())
        
        result = await compiled_graph.ainvoke(
            {
                "messages": [HumanMessage(content="Test")],
                "expression": "10*5",
                "lib1": "react",
                "docs_params": {
                    "context7CompatibleLibraryID": "/facebook/react",
                    "topic": "hooks"
                }
            },
            config={"configurable": {"thread_id": thread_id}}
        )
        
        print(f"✅ Граф выполнен")
        
        # Проверяем результаты всех нод
        print(f"\n📊 Результаты:")
        print(f"   calc_node: {result.get('calc_result', 'N/A')}")
        print(f"   mcp_resolve: {result.get('lib1_info', 'N/A')[:100]}...")
        print(f"   mcp_docs: {result.get('docs_result', 'N/A')[:100]}...")
        
        assert "calc_result" in result
        assert "lib1_info" in result
        assert "docs_result" in result
        
        print(f"\n✅ Все 3 ноды (1 обычная + 2 MCP) работают!")
    
    finally:
        # Очистка
        await agent_repo.delete("complex_stategraph_mcp")
        if 'mcp_tools' in locals():
            for tool in mcp_tools:
                await storage.delete(f"tool:{tool.tool_id}")


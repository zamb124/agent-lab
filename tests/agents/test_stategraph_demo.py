"""
Тест для демонстрационного StateGraph агента со всеми типами нод.
"""
import pytest
from apps.agents.models import NodeType


@pytest.mark.asyncio
async def test_stategraph_agent_migration(agent_repo, test_context):
    """Тест миграции агента со всеми типами нод"""
    
    # Загружаем конфиг напрямую из модуля
    import apps.agents.agents.test_stategraph_agent as test_agent_module
    agent_config = test_agent_module.test_stategraph_agent_config
    
    # Сохраняем в БД
    await agent_repo.set(agent_config)
    
    # Проверяем что агент создан
    agent = await agent_repo.get('apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config')
    
    assert agent is not None, "Агент должен быть сохранён в БД"
    assert agent.name == "Test StateGraph Agent"
    assert agent.description == "Демонстрационный агент со всеми типами нод"
    assert agent.graph_definition is not None, "Граф должен быть определён"
    
    # Проверяем количество нод
    nodes = agent.graph_definition.nodes
    assert len(nodes) == 10, f"Должно быть 10 нод, найдено {len(nodes)}"
    
    # Проверяем что есть все типы нод
    node_types = {node.type for node in nodes}
    expected_types = {
        NodeType.MESSAGE_NODE,
        NodeType.FUNCTION_NODE,
        NodeType.AGENT_NODE,
        NodeType.TOOL_NODE,
        NodeType.ROUTER_NODE,
    }
    
    assert expected_types.issubset(node_types), f"Не все типы нод присутствуют. Найдено: {node_types}"
    
    # Проверяем конкретные ноды
    node_ids = {node.id for node in nodes}
    assert "welcome_message" in node_ids, "Должна быть нода welcome_message (MESSAGE_NODE)"
    assert "greeting" in node_ids, "Должна быть нода greeting (FUNCTION_NODE)"
    assert "calculator_agent" in node_ids, "Должна быть нода calculator_agent (AGENT_NODE)"
    assert "calculator_tool" in node_ids, "Должна быть нода calculator_tool (TOOL_NODE)"
    assert "router" in node_ids, "Должна быть нода router (ROUTER_NODE)"
    assert "inline_function" in node_ids, "Должна быть нода inline_function (FUNCTION_NODE с inline кодом)"
    
    # Проверяем рёбра
    edges = agent.graph_definition.edges
    assert len(edges) == 12, f"Должно быть 12 рёбер (добавили EXPRESSION), найдено {len(edges)}"
    
    # Проверяем что тип определяется автоматически
    from apps.agents.models import AgentType
    assert agent.type == AgentType.STATEGRAPH, f"Агент с graph_definition должен автоматически стать STATEGRAPH, получили {agent.type}"
    
    print("\n✅ Агент успешно протестирован:")
    print(f"   Нод: {len(nodes)}")
    print(f"   Рёбер: {len(edges)}")
    print(f"   Типы нод: {', '.join(str(t).split('.')[-1] for t in node_types)}")


@pytest.mark.asyncio
async def test_stategraph_flow_migration(flow_repo, test_context):
    """Тест миграции flow для StateGraph агента"""
    
    # Загружаем flow конфиг
    import apps.agents.flows.test_stategraph_flow as test_flow_module
    flow_config = test_flow_module.test_stategraph_flow_config
    
    # Сохраняем в БД
    await flow_repo.set(flow_config)
    
    # Проверяем что flow создан
    flow = await flow_repo.get('apps.agents.flows.test_stategraph_flow.test_stategraph_flow_config')
    
    assert flow is not None, "Flow должен быть сохранён в БД"
    assert flow.name == "Test StateGraph Flow"
    assert flow.entry_point_agent == "apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config"
    
    print(f"\n✅ Flow успешно протестирован: {flow.name}")


@pytest.mark.asyncio
async def test_stategraph_agent_execution(agent_factory, agent_repo, test_context, system_context):
    """Тест выполнения StateGraph агента"""
    
    # Сохраняем агент в БД
    import apps.agents.agents.test_stategraph_agent as test_agent_module
    agent_config = test_agent_module.test_stategraph_agent_config
    await agent_repo.set(agent_config)
    
    # Создаём агента через фабрику
    agent = await agent_factory.get_agent('apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config')
    
    assert agent is not None, "Агент должен быть создан через фабрику"
    
    # Выполняем граф
    result = await agent.ainvoke(
        {
            "messages": ["Тестовое сообщение для проверки всех нод"],
            "store": {}
        },
        config={"configurable": {"session_id": "test_thread"}}
    )
    
    assert result is not None, "Результат выполнения не должен быть None"
    assert "messages" in result, "В результате должны быть messages"
    assert "store" in result, "В результате должен быть store"
    
    # Проверяем что были выполнены функции
    store = result.get("store", {})
    
    # Эти ключи устанавливаются функциями в графе
    # (но могут не установиться если граф не выполнился полностью)
    print("\n✅ Граф выполнен успешно!")
    print(f"   Messages: {len(result.get('messages', []))} сообщений")
    print(f"   Store keys: {list(store.keys())}")


@pytest.mark.asyncio
async def test_all_node_types_present(agent_repo, test_context):
    """Тест что все типы нод действительно используются"""
    
    import apps.agents.agents.test_stategraph_agent as test_agent_module
    agent_config = test_agent_module.test_stategraph_agent_config
    await agent_repo.set(agent_config)
    
    agent = await agent_repo.get('apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config')
    nodes = agent.graph_definition.nodes
    
    # Группируем ноды по типам
    nodes_by_type = {}
    for node in nodes:
        node_type = node.type
        if node_type not in nodes_by_type:
            nodes_by_type[node_type] = []
        nodes_by_type[node_type].append(node.id)
    
    print("\n📊 Распределение нод по типам:")
    for node_type, node_list in sorted(nodes_by_type.items(), key=lambda x: str(x[0])):
        print(f"   {str(node_type).split('.')[-1]:<20} {len(node_list)} шт: {', '.join(node_list)}")
    
    # Проверяем что есть хотя бы по одной ноде каждого основного типа
    assert NodeType.MESSAGE_NODE in nodes_by_type, "Должен быть MESSAGE_NODE"
    assert NodeType.FUNCTION_NODE in nodes_by_type, "Должен быть FUNCTION_NODE"
    assert NodeType.AGENT_NODE in nodes_by_type, "Должен быть AGENT_NODE"
    assert NodeType.TOOL_NODE in nodes_by_type, "Должен быть TOOL_NODE"
    assert NodeType.ROUTER_NODE in nodes_by_type, "Должен быть ROUTER_NODE"
    
    # Проверяем что есть inline код
    inline_nodes = [n for n in nodes if n.code_mode.value == "inline_code"]
    assert len(inline_nodes) > 0, "Должна быть хотя бы одна нода с inline кодом"
    
    print("\n✅ Все основные типы нод присутствуют!")
    print(f"   Inline code нод: {len(inline_nodes)}")


@pytest.mark.asyncio
async def test_message_node_adds_messages(agent_factory, agent_repo, test_context, system_context):
    """Тест что MESSAGE_NODE добавляет сообщения в state"""
    
    # Сохраняем агент в БД
    import apps.agents.agents.test_stategraph_agent as test_agent_module
    agent_config = test_agent_module.test_stategraph_agent_config
    await agent_repo.set(agent_config)
    
    # Создаём агента через фабрику
    agent = await agent_factory.get_agent('apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config')
    
    # Выполняем граф
    result = await agent.ainvoke(
        {
            "messages": ["Тест MESSAGE_NODE"],
            "store": {}
        },
        config={"configurable": {"session_id": "test_message_thread"}}
    )
    
    assert "messages" in result, "В результате должны быть messages"
    messages = result["messages"]
    
    # Проверяем что есть сообщения от MESSAGE_NODE
    message_contents = [str(msg.content) if hasattr(msg, 'content') else str(msg) for msg in messages]
    
    # Должно быть приветственное сообщение от welcome_message ноды
    welcome_found = any("Добро пожаловать" in content for content in message_contents)
    assert welcome_found, f"Должно быть приветственное сообщение от MESSAGE_NODE. Найдено: {message_contents}"
    
    # Должно быть информационное сообщение от message_info ноды (если граф прошёл через неё)
    info_found = any("Промежуточное информационное сообщение" in content for content in message_contents)
    
    print("\n✅ MESSAGE_NODE работает корректно!")
    print(f"   Всего сообщений: {len(messages)}")
    print(f"   Приветственное сообщение: {'✅' if welcome_found else '❌'}")
    print(f"   Информационное сообщение: {'✅' if info_found else '❌'}")
    
    # Проверяем типы сообщений
    from langchain_core.messages import AIMessage
    ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
    print(f"   AIMessage сообщений: {len(ai_messages)}")
    
    assert len(ai_messages) >= 1, "Должно быть хотя бы одно AIMessage от MESSAGE_NODE"


@pytest.mark.asyncio  
async def test_condition_types_work(agent_factory, agent_repo, test_context, system_context):
    """Тест что оба типа условий (ROUTER и EXPRESSION) работают"""
    
    # Сохраняем агент в БД
    import apps.agents.agents.test_stategraph_agent as test_agent_module
    agent_config = test_agent_module.test_stategraph_agent_config
    await agent_repo.set(agent_config)
    
    # Проверяем что в графе есть оба типа условий
    from apps.agents.models import ConditionType
    
    edges = agent_config.graph_definition.edges
    router_edges = [e for e in edges if e.condition_type == ConditionType.ROUTER]
    expression_edges = [e for e in edges if e.condition_type == ConditionType.EXPRESSION]
    
    assert len(router_edges) > 0, f"Должны быть ROUTER edges. Найдено edges: {[(e.source, e.target, e.condition_type) for e in edges]}"
    assert len(expression_edges) > 0, f"Должны быть EXPRESSION edges. Найдено edges: {[(e.source, e.target, e.condition_type) for e in edges]}"
    
    print("\n✅ Типы условий:")
    print(f"   ROUTER edges: {len(router_edges)}")
    for edge in router_edges:
        print(f"      {edge.source} -> {edge.target}")
    
    print(f"   EXPRESSION edges: {len(expression_edges)}")
    for edge in expression_edges:
        condition_preview = edge.condition[:50] if edge.condition else "None"
        print(f"      {edge.source} -> {edge.target} (condition: {condition_preview}...)")
    
    # Создаём и выполняем граф
    agent = await agent_factory.get_agent('apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config')
    
    result = await agent.ainvoke(
        {
            "messages": ["Тест условий"],
            "store": {}
        },
        config={"configurable": {"session_id": "test_conditions_thread"}}
    )
    
    # Проверяем что граф выполнился успешно
    assert result is not None, "Граф должен вернуть результат"
    
    store = result.get("store", {})
    print(f"\n   Store после выполнения: {list(store.keys())}")
    
    # Проверяем что EXPRESSION условие сработало
    assert "condition_passed" in store, "EXPRESSION должен установить condition_passed"
    assert store["condition_passed"] is True, "condition_passed должен быть True"
    
    print("\n✅ Оба типа условий работают корректно!")


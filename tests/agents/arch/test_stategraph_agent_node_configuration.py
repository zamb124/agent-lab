"""
Тест для проверки разных способов конфигурации AGENT_NODE в StateGraph.

Проверяет что нода типа AGENT_NODE может быть настроена:
1. Через params['agent_id']
2. Через function_class
3. Через id ноды (fallback)
"""
import pytest
from apps.agents.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig, LLMConfig,
    GraphDefinition, GraphNode, GraphEdge, NodeType
)
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_agent_node_with_params_agent_id(migrated_db,  flow_factory, mock_llm, agent_repo, flow_repo, system_context):
    """Тест: AGENT_NODE с agent_id в params"""
    
    # Создаем граф с нодой агента через params['agent_id']
    graph_def = GraphDefinition(
        nodes=[
            GraphNode(
                id="calc_node",
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                params={"agent_id": "apps.agents.agents.calculator.agent.CalculatorAgent"}
            )
        ],
        edges=[
            GraphEdge(source="START", target="calc_node"),
            GraphEdge(source="calc_node", target="END")
        ],
        entry_point="START"
    )
    
    agent_config = AgentConfig(
        agent_id="test_agent_params",
        name="Test Agent with params",
        description="Тест агента с agent_id в params",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="manual"
    )
    
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_flow_params",
        name="Test Flow params",
        description="Тест флоу с agent_id в params",
        entry_point_agent="test_agent_params",
        platforms={"api": {}}
    )
    
    await flow_repo.set(flow_config)
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            responses={
                "посчитай": "Результат: 12",
            },
            default_response="Готово"
        )
    
    # Устанавливаем llm_config для CalculatorAgent если его нет
    from apps.agents.container import get_agents_container
    agent_factory = get_agents_container().agent_factory
    calculator_agent = await agent_factory.get_agent("apps.agents.agents.calculator.agent.CalculatorAgent")
    if calculator_agent and calculator_agent.config and not calculator_agent.config.llm_config:
        calculator_agent.config.llm_config = LLMConfig(model="mock-gpt-4", context_window=8192)
        await agent_factory.agent_repository.set(calculator_agent.config)
    
    # Проверяем что граф компилируется
    flow = await flow_factory.get_flow("test_flow_params")
    
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 5 + 7")]},
        config={"configurable": {"session_id": "test_params"}}
    )
    
    assert "messages" in result
    print("✅ Тест с params['agent_id'] прошёл успешно")


@pytest.mark.asyncio
async def test_agent_node_with_function_class(migrated_db,  flow_factory, mock_llm, agent_repo, flow_repo, system_context):
    """Тест: AGENT_NODE с function_class"""
    
    # Создаем граф с нодой агента через function_class
    graph_def = GraphDefinition(
        nodes=[
            GraphNode(
                id="calc_node",
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                function_class="apps.agents.agents.calculator.agent.CalculatorAgent"
            )
        ],
        edges=[
            GraphEdge(source="START", target="calc_node"),
            GraphEdge(source="calc_node", target="END")
        ],
        entry_point="START"
    )
    
    agent_config = AgentConfig(
        agent_id="test_agent_class",
        name="Test Agent with function_class",
        description="Тест агента с function_class",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="manual"
    )
    
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_flow_class",
        name="Test Flow class",
        description="Тест флоу с function_class",
        entry_point_agent="test_agent_class",
        platforms={"api": {}}
    )
    
    await flow_repo.set(flow_config)
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            responses={
                "посчитай": "Результат: 12",
            },
            default_response="Готово"
        )
    
    # Устанавливаем llm_config для CalculatorAgent если его нет
    from apps.agents.container import get_agents_container
    agent_factory = get_agents_container().agent_factory
    calculator_agent = await agent_factory.get_agent("apps.agents.agents.calculator.agent.CalculatorAgent")
    if calculator_agent and calculator_agent.config and not calculator_agent.config.llm_config:
        calculator_agent.config.llm_config = LLMConfig(model="mock-gpt-4", context_window=8192)
        await agent_factory.agent_repository.set(calculator_agent.config)
    
    # Проверяем что граф компилируется
    flow = await flow_factory.get_flow("test_flow_class")
    
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 5 + 7")]},
        config={"configurable": {"session_id": "test_class"}}
    )
    
    assert "messages" in result
    print("✅ Тест с function_class прошёл успешно")


@pytest.mark.asyncio
async def test_agent_node_with_id_fallback(migrated_db,  flow_factory, mock_llm, agent_factory, agent_repo, flow_repo, system_context):
    """Тест: AGENT_NODE с id ноды как agent_id (fallback)"""
    
    # Создаем граф с нодой агента без agent_id и function_class
    # ID ноды = agent_id агента
    graph_def = GraphDefinition(
        nodes=[
            GraphNode(
                id="apps.agents.agents.calculator.agent.CalculatorAgent",
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                params={}  # НЕТ agent_id
                # НЕТ function_class
            )
        ],
        edges=[
            GraphEdge(source="START", target="apps.agents.agents.calculator.agent.CalculatorAgent"),
            GraphEdge(source="apps.agents.agents.calculator.agent.CalculatorAgent", target="END")
        ],
        entry_point="START"
    )
    
    agent_config = AgentConfig(
        agent_id="test_agent_fallback",
        name="Test Agent with id fallback",
        description="Тест агента с id как agent_id",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="manual"
    )
    
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_flow_fallback",
        name="Test Flow fallback",
        description="Тест флоу с id как agent_id",
        entry_point_agent="test_agent_fallback",
        platforms={"api": {}}
    )
    
    await flow_repo.set(flow_config)
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            responses={
                "посчитай": "Результат: 12",
            },
            default_response="Готово"
        )
    
    # Устанавливаем llm_config для CalculatorAgent если его нет
    from apps.agents.container import get_agents_container
    agent_factory = get_agents_container().agent_factory
    calculator_agent = await agent_factory.get_agent("apps.agents.agents.calculator.agent.CalculatorAgent")
    if calculator_agent and calculator_agent.config and not calculator_agent.config.llm_config:
        calculator_agent.config.llm_config = LLMConfig(model="mock-gpt-4", context_window=8192)
        await agent_factory.agent_repository.set(calculator_agent.config)
    
    # Проверяем что граф компилируется
    flow = await flow_factory.get_flow("test_flow_fallback")
    
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 5 + 7")]},
        config={"configurable": {"session_id": "test_fallback"}}
    )
    
    assert "messages" in result
    print("✅ Тест с id как agent_id (fallback) прошёл успешно")


@pytest.mark.asyncio
async def test_agent_node_short_id_fallback(migrated_db,  flow_factory, agent_factory, agent_repo, flow_repo):
    """Тест: AGENT_NODE с коротким id (как в логах ошибки)"""
    
    # Воспроизводим ошибку из логов: id="calculator" без agent_id и function_class
    graph_def = GraphDefinition(
        nodes=[
            GraphNode(
                id="calculator",  # КОРОТКИЙ ID
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                params={}  # НЕТ agent_id
                # НЕТ function_class
            )
        ],
        edges=[
            GraphEdge(source="START", target="calculator"),
            GraphEdge(source="calculator", target="END")
        ],
        entry_point="START"
    )
    
    agent_config = AgentConfig(
        agent_id="test_agent_short_id",
        name="Test Agent with short id",
        description="Тест агента с коротким id",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="manual"
    )
    
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_flow_short_id",
        name="Test Flow short id",
        description="Тест флоу с коротким id",
        entry_point_agent="test_agent_short_id",
        platforms={"api": {}}
    )
    
    await flow_repo.set(flow_config)
    
    # Проверяем что получаем понятную ошибку
    try:
        flow = await flow_factory.get_flow("test_flow_short_id")
        agent = await agent_factory.get_agent("test_agent_short_id")
        await agent.compile_graph()
        
        pytest.fail("Должна была быть ошибка, но её не было")
    except ValueError as e:
        # Проверяем что ошибка понятная
        error_msg = str(e)
        assert "calculator" in error_msg.lower()
        assert "не найден" in error_msg.lower() or "not found" in error_msg.lower()
        print(f"✅ Получена ожидаемая ошибка: {error_msg}")


@pytest.mark.asyncio
async def test_agent_node_error_message_quality(migrated_db,  flow_factory, agent_factory, agent_repo, flow_repo):
    """Тест: качество сообщения об ошибке для некорректной ноды"""
    
    # Создаем граф с ПОЛНОСТЬЮ пустой нодой агента
    graph_def = GraphDefinition(
        nodes=[
            GraphNode(
                id="",  # ПУСТОЙ ID
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                params={}
            )
        ],
        edges=[
            GraphEdge(source="START", target=""),
            GraphEdge(source="", target="END")
        ],
        entry_point="START"
    )
    
    agent_config = AgentConfig(
        agent_id="test_agent_empty",
        name="Test Agent empty",
        description="Тест агента с пустой нодой",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="manual"
    )
    
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_flow_empty",
        name="Test Flow empty",
        description="Тест флоу с пустой нодой",
        entry_point_agent="test_agent_empty",
        platforms={"api": {}}
    )
    
    await flow_repo.set(flow_config)
    
    # Проверяем что получаем информативную ошибку
    try:
        flow = await flow_factory.get_flow("test_flow_empty")
        agent = await agent_factory.get_agent("test_agent_empty")
        await agent.compile_graph()
        
        pytest.fail("Должна была быть ошибка, но её не было")
    except ValueError as e:
        error_msg = str(e)
        # Проверяем что ошибка содержит полезную информацию
        assert "params" in error_msg.lower() or "function_class" in error_msg.lower()
        print(f"✅ Получена информативная ошибка: {error_msg}")


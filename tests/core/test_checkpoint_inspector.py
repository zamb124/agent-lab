"""
Тесты для инспектора чекпоинтеров LangGraph.

Проверяет:
1. ReAct агент с калькулятором - несколько вызовов и анализ результатов
2. StateGraph агент с нодами - проверка работы инспектора
"""

import pytest
from langchain_core.messages import HumanMessage

from apps.agents.services.state_inspector import StateInspector
from apps.agents.models import AgentConfig, AgentType, GraphDefinition, GraphNode, GraphEdge, NodeType, CodeMode, LLMConfig


@pytest.mark.asyncio
async def test_checkpoint_inspector_react_agent_with_calculator(
    migrated_db,  agent_factory, agent_repo, mock_llm, test_helpers, unique_id
):
    """
    Тест 1: ReAct агент с калькулятором.
    
    Создаем ReAct агента с тулом калькулятор, делаем несколько вызовов,
    проверяем что инспектор правильно показывает:
    - Историю чекпоинтеров
    - Вызовы инструментов
    - Связи между чекпоинтерами
    """
    calculator_tool = test_helpers.create_inline_tool(
        tool_id="calculate_tool",
        function_name="calculate_tool",
        function_body='''
async def calculate_tool(a: int, b: int, operation: str = "add") -> str:
    """Выполняет математические операции"""
    if operation == "add":
        result = a + b
    elif operation == "multiply":
        result = a * b
    elif operation == "subtract":
        result = a - b
    else:
        result = a + b
    return f"Результат: {a} {operation} {b} = {result}"
''',
        description="Калькулятор для математических операций"
    )

    await test_helpers.create_simple_agent(
        agent_id="calc_react_agent",
        name="Calculator ReAct Agent",
        prompt="Ты математический помощник. Используй calculate_tool для вычислений.",
        tools=[calculator_tool]
    )

    agent = await agent_factory.get_agent("calc_react_agent")
    thread_id = unique_id("calc_test")

    mock_llm.configure(
        tool_responses={
            "сколько будет": {"tool": "calculate_tool", "args": {"a": 10, "b": 5, "operation": "add"}},
            "умножь": {"tool": "calculate_tool", "args": {"a": 7, "b": 3, "operation": "multiply"}},
        },
        default_response="Выполняю вычисление с помощью калькулятора"
    )

    config = {"configurable": {"thread_id": thread_id}}

    result1 = await agent.ainvoke(
        {"messages": [HumanMessage(content="Сколько будет 10 + 5?")]},
        config=config
    )

    assert "messages" in result1

    result2 = await agent.ainvoke(
        {"messages": [HumanMessage(content="Умножь 7 на 3")]},
        config=config
    )

    assert "messages" in result2

    inspector = StateInspector()

    history = await inspector.get_checkpoint_history(thread_id)
    assert len(history) > 0, "Должна быть история чекпоинтеров"

    connections = await inspector.get_checkpoint_connections(thread_id)
    assert "connections" in connections
    assert "summary" in connections
    assert connections["summary"]["total_checkpoints"] > 0

    tool_calls_found = 0
    for checkpoint in history:
        if checkpoint.get("tool_calls"):
            tool_calls_found += len(checkpoint["tool_calls"])
            for tool_call in checkpoint["tool_calls"]:
                assert "name" in tool_call
                assert tool_call["name"] == "calculate_tool"

    assert tool_calls_found > 0, "Должны быть найдены вызовы инструментов"

    timeline = await inspector.get_timeline(thread_id)
    assert "timeline" in timeline
    assert "summary" in timeline
    assert len(timeline["timeline"]) > 0
    assert "tool_stats" in timeline["summary"]
    assert "calculate_tool" in timeline["summary"]["tool_stats"]
    assert timeline["summary"]["tool_stats"]["calculate_tool"] >= 1

    print("✅ Тест 1 пройден: ReAct агент с калькулятором")
    print(f"   Найдено чекпоинтеров: {len(history)}")
    print(f"   Найдено вызовов инструментов: {tool_calls_found}")
    print(f"   Статистика инструментов: {timeline['summary']['tool_stats']}")


@pytest.mark.asyncio
async def test_checkpoint_inspector_stategraph_agent(
    migrated_db,  agent_factory, agent_repo, mock_llm, test_helpers, unique_id
):
    """
    Тест 2: StateGraph агент с нодами.
    
    Создаем StateGraph агента с несколькими нодами, выполняем несколько шагов,
    проверяем что инспектор правильно показывает:
    - Последовательность выполнения нод
    - Переменные состояния (store)
    - Связи между чекпоинтерами
    """
    calculator_tool = test_helpers.create_inline_tool(
        tool_id="calc_add",
        function_name="calc_add",
        function_body='''
async def calc_add(x: int, y: int) -> str:
    """Сложение двух чисел"""
    return f"{x} + {y} = {x + y}"
''',
        description="Сложение"
    )

    await test_helpers.create_simple_agent(
        agent_id="calc_sub_agent",
        name="Calculator Sub Agent",
        prompt="Ты простой калькулятор",
        tools=[calculator_tool]
    )

    agent_config = AgentConfig(
        agent_id="test_stategraph_inspector",
        name="Test StateGraph Inspector",
        description="Тестовый StateGraph агент для инспектора",
        type=AgentType.STATEGRAPH,
        graph_definition=GraphDefinition(
            nodes=[
                GraphNode(
                    id="init_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
async def init_node(state):
    '''Инициализация нода - сохраняет данные в store'''
    if "store" not in state:
        state["store"] = {}
    state["store"]["counter"] = 1
    state["store"]["message"] = "Инициализация выполнена"
    return state
""",
                ),
                GraphNode(
                    id="calc_agent_node",
                    type=NodeType.AGENT_NODE,
                    params={"agent_id": "calc_sub_agent"},
                ),
                GraphNode(
                    id="result_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
async def result_node(state):
    '''Финальная нода - обрабатывает результат'''
    if "store" not in state:
        state["store"] = {}
    state["store"]["counter"] = state["store"].get("counter", 0) + 1
    state["store"]["finalized"] = True
    return state
""",
                ),
            ],
            edges=[
                GraphEdge(source="START", target="init_node"),
                GraphEdge(source="init_node", target="calc_agent_node"),
                GraphEdge(source="calc_agent_node", target="result_node"),
                GraphEdge(source="result_node", target="END"),
            ],
            entry_point="init_node",
        ),
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
    )

    await agent_repo.set(agent_config)

    agent = await agent_factory.get_agent("test_stategraph_inspector")
    thread_id = unique_id("stategraph_test")

    mock_llm.configure(
        tool_responses={
            "вычисли": {"tool": "calc_add", "args": {"x": 15, "y": 25}},
        },
        default_response="Выполняю вычисление"
    )

    config = {"configurable": {"thread_id": thread_id}}

    result = await agent.ainvoke(
        {
            "messages": [HumanMessage(content="Вычисли 15 + 25")],
            "store": {},
            "remaining_steps": 25,
        },
        config=config
    )

    assert "messages" in result
    assert "store" in result

    inspector = StateInspector()

    history = await inspector.get_checkpoint_history(thread_id)
    assert len(history) > 0

    connections = await inspector.get_checkpoint_connections(thread_id)
    assert "connections" in connections
    assert connections["summary"]["total_checkpoints"] > 0

    store_variables_found = False
    for checkpoint in history:
        store_vars = checkpoint.get("store_variables", {})
        if store_vars:
            store_variables_found = True
            assert "counter" in store_vars or "message" in store_vars or "finalized" in store_vars

    assert store_variables_found, "Должны быть найдены переменные store"

    timeline = await inspector.get_timeline(thread_id, include_values=False)
    assert "timeline" in timeline
    assert len(timeline["timeline"]) > 0

    steps_with_store = 0
    for entry in timeline["timeline"]:
        if entry.get("store_variables"):
            steps_with_store += 1

    assert steps_with_store > 0, "Должны быть шаги с переменными store"

    print("✅ Тест 2 пройден: StateGraph агент с нодами")
    print(f"   Найдено чекпоинтеров: {len(history)}")
    print(f"   Найдено связей: {len(connections['connections'])}")
    print(f"   Шагов с переменными store: {steps_with_store}")


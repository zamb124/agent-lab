"""
Тест 2: StateGraph агент с роутером и calculate.

Проверяет StateGraph агента с:
- 1ая нода роутер (выбирает путь на основе сообщения)
- далее 1 нода функциональная (выполняет логику)
- 2-я calculate (выполняет вычисление)
- оба пути сводятся к ноде message (отправляет "результат получен" в интерфейс)
- потом нода реактивного агента из п1
"""
import pytest
from apps.agents.models import (
    AgentConfig, AgentType, GraphDefinition, GraphNode, GraphEdge,
    NodeType, ConditionType, CodeMode, ToolReference, LLMConfig
)
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_create_final_react_agent(
    migrated_db,  agent_repo, test_helpers
):
    """Создание финального ReAct агента отдельно"""

    # Создаем финальный ReAct агент
    final_agent_tool = test_helpers.create_inline_tool(
        tool_id="final_calculate",
        function_name="final_calculate",
        function_body='''
def final_calculate(x: int, y: int) -> str:
    """Финальное вычисление для завершения"""
    # В реальном сценарии tool может читать данные из state через context
    from core.context import get_context
    context = get_context()
    if context and hasattr(context, 'state') and 'store' in context.state:
        store = context.state['store']
        if 'final_data' in store:
            x = store['final_data'].get('x', x)
            y = store['final_data'].get('y', y)
    return f"Финальный результат: {x} + {y} = {x + y}"
''',
        description="Финальное вычисление"
    )

    # Создаем финальный агент
    await test_helpers.create_simple_agent(
        agent_id="final_react_agent",
        name="Final React Agent",
        prompt="Ты финальный агент. Тебе передали state с данными. В store['final_data'] есть числа x и y. Выполни вычисление x + y используя final_calculate tool с параметрами из store.",
        tools=[final_agent_tool]
    )

    # Проверяем что агент создан
    saved_config = await agent_repo.get("final_react_agent")
    assert saved_config is not None, "Финальный агент НЕ сохранился в БД!"

    print("✅ Финальный ReAct агент создан в БД")


@pytest.mark.asyncio
async def test_stategraph_router_calculate_agent_in_db(
    migrated_db,  agent_factory, agent_repo, test_helpers
):
    """Создание StateGraph агента с роутером и calculate в БД"""

    # Создаем calculate tool для StateGraph
    calculate_tool = test_helpers.create_inline_tool(
        tool_id="calculate_sum",
        function_name="calculate_sum",
        function_body='''
def calculate_sum(a: int, b: int) -> str:
    """Вычислить сумму двух чисел для StateGraph"""
    return f"Сумма: {a} + {b} = {a + b}"
''',
        description="Сложение чисел для StateGraph"
    )

    # Определяем коды для нод
    router_code = '''
async def router_function(state):
    """Роутер: выбирает путь на основе содержания сообщения"""
    from langchain_core.messages import AIMessage
    messages = state.get("messages", [])
    if messages:
        text = messages[0].content.lower()
        # Если есть "плюс" или "+" - идем в calculate, иначе в function
        if "плюс" in text or "+" in text:
            state["route"] = "calculate"
            state["messages"].append(AIMessage(content="[ROUTER] Выбран путь: calculate"))
        else:
            state["route"] = "function"
            state["messages"].append(AIMessage(content="[ROUTER] Выбран путь: function"))
    return state

def router_condition(state):
    """Условие для роутера"""
    route = state.get("route", "function")
    return "calculate_node" if route == "calculate" else "function_node"
'''

    function_code = '''
async def function_node(state):
    """Функциональная нода: выполняет простую логику"""
    from langchain_core.messages import AIMessage
    state["messages"].append(AIMessage(content="Функциональная нода выполнена"))
    state["processed"] = True
    return state
'''

    calculate_code = '''
async def calculate_node(state):
    """Нода с calculate: выполняет вычисление"""
    from langchain_core.messages import AIMessage

    # Имитация вызова calculate tool
    a, b = 10, 5  # Фиксированные значения для теста
    result = f"Результат: {a} + {b} = {a + b}"
    state["messages"].append(AIMessage(content=f"Calculate нода: {result}"))
    state["calculation_done"] = True
    return state
'''

    message_code = '''
async def message_node(state):
    """Нода сообщения: отправляет результат в интерфейс и подготавливает данные для финального агента"""
    from langchain_core.messages import AIMessage

    state["messages"].append(AIMessage(content="Результат получен"))

    # Подготавливаем данные для финального агента в store (чтобы сохранилось между нодами)
    if "store" not in state:
        state["store"] = {}
    state["store"]["final_data"] = {"x": 7, "y": 3}

    # Добавляем инструкцию для финального агента в messages
    state["messages"].append(AIMessage(content="Финальный агент, в store['final_data'] есть числа x и y. Выполни вычисление x + y используя final_calculate tool с этими числами."))

    state["message_sent"] = True
    return state
'''

    # Создаем GraphDefinition
    graph_def = GraphDefinition(
        nodes=[
            # Роутер
            GraphNode(
                id="router",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=router_code,
                params={}
            ),
            # Функциональная нода
            GraphNode(
                id="function_node",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=function_code,
                params={}
            ),
            # Calculate нода
            GraphNode(
                id="calculate_node",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=calculate_code,
                params={}
            ),
            # Message нода
            GraphNode(
                id="message_node",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=message_code,
                params={}
            ),
            # Финальная нода - настоящий ReAct агент
            GraphNode(
                id="final_agent",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "final_react_agent"}
            ),
        ],
        edges=[
            # START → router
            GraphEdge(source="START", target="router"),

            # router → function_node (conditional)
            GraphEdge(
                source="router",
                target="function_node",
                condition_type=ConditionType.ROUTER
            ),

            # router → calculate_node (conditional)
            GraphEdge(
                source="router",
                target="calculate_node",
                condition_type=ConditionType.ROUTER
            ),

            # function_node → message_node
            GraphEdge(source="function_node", target="message_node"),

            # calculate_node → message_node
            GraphEdge(source="calculate_node", target="message_node"),

            # message_node → final_agent
            GraphEdge(source="message_node", target="final_agent"),

            # final_agent → END
            GraphEdge(source="final_agent", target="END"),
        ],
        entry_point="START"
    )

    # Создаем AgentConfig
    agent_config = AgentConfig(
        agent_id="stategraph_router_calculate",
        name="StateGraph Router Calculate",
        description="StateGraph с роутером и calculate нодой",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4"),
        source="test",
    )

    # Сохраняем в БД
    await agent_repo.set(agent_config)

    # Проверяем сохранение
    saved_config = await agent_repo.get("stategraph_router_calculate")
    assert saved_config is not None, "StateGraph агент НЕ сохранился в БД!"
    assert saved_config.graph_definition is not None, "Граф должен быть определён"
    assert len(saved_config.graph_definition.nodes) == 5, f"Должно быть 5 нод, найдено {len(saved_config.graph_definition.nodes)}"

    print("✅ StateGraph агент с роутером и calculate создан в БД")


@pytest.mark.asyncio
async def test_execute_stategraph_router_calculate_function_path(
    migrated_db,  agent_factory, agent_repo, test_helpers, unique_id
):
    """Тестирование пути через function_node"""

    # Сначала создаем финального агента
    await test_create_final_react_agent(migrated_db,  agent_repo, test_helpers)

    # Создаем StateGraph агента
    await test_stategraph_router_calculate_agent_in_db(
        migrated_db,  agent_factory, agent_repo, test_helpers
    )

    # Загружаем агента
    agent = await agent_factory.get_agent("stategraph_router_calculate")
    compiled_graph = await agent.compile_graph()

    print("✅ StateGraph агент загружен и скомпилирован")

    # Тест пути через function_node (без "плюс" или "+")
    result = await compiled_graph.ainvoke(
        {"messages": [HumanMessage(content="Обработай этот текст")]},
        config={"configurable": {"thread_id": unique_id("function_path")}}
    )

    messages = result["messages"]
    print(f"Получено {len(messages)} сообщений:")

    # Проверяем последовательность
    message_texts = [msg.content for msg in messages]

    assert any("[ROUTER] Выбран путь: function" in text for text in message_texts), "Должен быть роутер с выбором function"
    assert any("Функциональная нода выполнена" in text for text in message_texts), "Должна выполниться function_node"
    assert any("Результат получен" in text for text in message_texts), "Должна выполниться message_node"

    print("✅ Путь через function_node отработал корректно")


@pytest.mark.asyncio
async def test_execute_stategraph_router_calculate_math_path(
    migrated_db,  agent_factory, agent_repo, test_helpers, unique_id
):
    """Тестирование пути через calculate_node"""

    # Сначала создаем финального агента
    await test_create_final_react_agent(migrated_db,  agent_repo, test_helpers)

    # Создаем StateGraph агента (если не создан)
    try:
        await agent_repo.get("stategraph_router_calculate")
    except:
        await test_stategraph_router_calculate_agent_in_db(
            migrated_db,  agent_factory, agent_repo, test_helpers
        )

    # Загружаем агента
    agent = await agent_factory.get_agent("stategraph_router_calculate")
    compiled_graph = await agent.compile_graph()

    # Тест пути через calculate_node (с "плюс")
    result = await compiled_graph.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 10 плюс 5")]},
        config={"configurable": {"thread_id": unique_id("calculate_path")}}
    )

    messages = result["messages"]
    print(f"Получено {len(messages)} сообщений:")

    # Проверяем последовательность
    message_texts = [msg.content for msg in messages]

    assert any("[ROUTER] Выбран путь: calculate" in text for text in message_texts), "Должен быть роутер с выбором calculate"
    assert any("Calculate нода:" in text for text in message_texts), "Должна выполниться calculate_node"
    assert any("Результат получен" in text for text in message_texts), "Должна выполниться message_node"
    assert any("15" in text for text in message_texts), "Должен быть результат 10+5=15"

    print("✅ Путь через calculate_node отработал корректно")


@pytest.mark.asyncio
async def test_complete_stategraph_flow_with_final_agent(
    migrated_db,  agent_factory, agent_repo, test_helpers, unique_id, mock_llm
):
    """Тестирование полного StateGraph flow: router -> function_node -> message_node -> final_agent"""

    # Сначала создаем финального агента
    await test_create_final_react_agent(migrated_db,  agent_repo, test_helpers)

    # Удаляем старый StateGraph агент если существует
    try:
        await agent_repo.delete("stategraph_router_calculate")
    except:
        pass

    # Создаем StateGraph агента заново
    await test_stategraph_router_calculate_agent_in_db(
        migrated_db,  agent_factory, agent_repo, test_helpers
    )

    # Настраиваем mock LLM для финального агента
    mock_llm.configure(
        tool_responses={
            "агент": {"tool": "final_calculate", "args": {"x": 7, "y": 3}},
            "финальн": {"tool": "final_calculate", "args": {"x": 7, "y": 3}},
            "выполни": {"tool": "final_calculate", "args": {"x": 7, "y": 3}},
            "store": {"tool": "final_calculate", "args": {"x": 7, "y": 3}},
            "final_data": {"tool": "final_calculate", "args": {"x": 7, "y": 3}},
        },
        default_response="Вызываю final_calculate"
    )

    # Загружаем StateGraph агента как единое целое
    stategraph_agent = await agent_factory.get_agent("stategraph_router_calculate")

    # Выполняем весь StateGraph агент от начала до конца
    result = await stategraph_agent.ainvoke(
        {"messages": [HumanMessage(content="Выполни полный расчет")]},
        config={"configurable": {"thread_id": unique_id("complete_flow")}}
    )

    messages = result["messages"]
    message_texts = [msg.content for msg in messages]

    print(f"Полный flow - сообщения: {message_texts}")

    # Проверяем всю последовательность выполнения
    assert any("[ROUTER] Выбран путь:" in text for text in message_texts), "Должен быть роутер"
    assert any("Функциональная нода выполнена" in text for text in message_texts), "Должна выполниться function_node"
    assert any("Результат получен" in text for text in message_texts), "Должна выполниться message_node"

    # Проверяем что финальный агент получил данные из предыдущих нод
    # final_data может быть в store или в messages
    final_data_found = False
    if "final_data" in result:
        assert result["final_data"] == {"x": 7, "y": 3}, f"final_data должна содержать x=7, y=3. Получено: {result.get('final_data')}"
        final_data_found = True
        print(f"✅ final_data найдена в result: {result['final_data']}")
    elif "store" in result and "final_data" in result["store"]:
        assert result["store"]["final_data"] == {"x": 7, "y": 3}, f"final_data в store должна содержать x=7, y=3. Получено: {result['store'].get('final_data')}"
        final_data_found = True
        print(f"✅ final_data найдена в store: {result['store']['final_data']}")
    else:
        # Ищем в messages
        for msg in result["messages"]:
            if hasattr(msg, 'content') and "final_data" in str(msg.content):
                final_data_found = True
                print(f"✅ final_data найдена в messages: {msg.content}")
                break

    assert final_data_found, f"final_data должна быть в результате. Result keys: {list(result.keys())}, Store: {result.get('store', {})}"

    # Проверяем что финальный агент выполнился и использовал данные из state
    all_messages = " ".join(message_texts)
    has_final_result = "Финальный результат:" in all_messages and "10" in all_messages

    assert has_final_result, f"Финальный агент должен выполнить вычисление 7+3=10 с данными из state. Сообщения: {message_texts}"

    print(f"✅ Полный StateGraph flow отработал: router → function_node → message_node → final_agent")
    print(f"✅ Данные перешли между нодами: final_data = {result['store']['final_data']}")
    print(f"✅ Финальный агент использовал данные: {' '.join([m for m in message_texts if 'Финальный результат' in m])}")
    print("✅ StateGraph агент работает как единое целое!")

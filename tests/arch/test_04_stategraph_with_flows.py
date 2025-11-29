"""
Тест 4: StateGraph агент с флоу нодами в БД.

Проверяет что можно создать StateGraph агента где ноды 
вызывают другие флоу, и все это работает из БД.
"""
import pytest
from apps.agents.models import (
    AgentConfig, AgentType, CodeMode, LLMConfig,
    GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType
)
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_create_stategraph_with_flow_nodes(migrated_db,  test_helpers, agent_repo):
    """Создание StateGraph агента с нодами-флоу"""
        
        # 1. СОЗДАЕМ СУПЕР-АГЕНТА С ФЛОУ НОДАМИ
        
        # Inline код для router
    super_router_code = '''
def super_router_function(state):
    """Супер роутер который выбирает между математикой и погодой"""
    user_input = state["messages"][0].content
    
    state["original_question"] = user_input
    
    if any(kw in user_input.lower() for kw in ["посчитай", "вычисли", "сколько", "+", "-", "*", "/"]):
        state["selected_flow"] = "math"
        return state
    else:
        state["selected_flow"] = "weather"
        return state

def super_router_condition(state):
    """Условие для выбора флоу"""
    flow_type = state["selected_flow"]
    # Возвращаем имена нод, а не типы флоу
    if flow_type == "math":
        return "math_flow"
    elif flow_type == "weather":
        return "weather_flow"
    else:
        return "math_flow"  # fallback
'''
        
        # Inline код для math flow ноды
    math_flow_code = '''
async def math_flow_node(state):
    """Нода которая вызывает математический флоу"""
    from apps.agents.services.flow_factory import FlowFactory
    from apps.agents.container import get_agents_container
    factory = get_agents_container().flow_factory
    smart_flow = await factory.get_flow("apps.agents.flows.smart_flow.smart_flow_config")  # Используем существующий smart_flow
    
    result = await smart_flow.ainvoke(
        {"messages": [{"role": "user", "content": state["original_question"]}]},
        config={"configurable": {"session_id": f"math_subflow_{hash(state['original_question'])}"}}
    )
    
    state["messages"] = result["messages"]
    state["flow_result"] = "math_completed"
    return state
'''
        
        # Inline код для weather flow ноды  
    weather_flow_code = '''
async def weather_flow_node(state):
    """Нода которая вызывает погодный флоу"""
    from apps.agents.services.flow_factory import FlowFactory
    from apps.agents.container import get_agents_container
    factory = get_agents_container().flow_factory
    weather_flow = await factory.get_flow("apps.agents.flows.weather_flow.weather_flow_config")  # Используем существующий weather_flow
    
    result = await weather_flow.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"session_id": f"weather_subflow_{hash(state['original_question'])}"}}
    )
    
    state["messages"] = result["messages"]
    state["flow_result"] = "weather_completed"
    return state
'''
        
        # Inline код для finalizer
    finalizer_code = '''
async def finalizer_node(state):
    """Финализирует результат супер-агента"""
    from langchain_core.messages import AIMessage
    
    flow_type = state.get("selected_flow", "unknown")
    result_status = state.get("flow_result", "unknown")
    
    summary = f"Супер-агент обработал {flow_type} запрос. Статус: {result_status}"
    
    # Добавляем summary к результату
    state["messages"].append(AIMessage(content=f"\\n\\n--- СУПЕР-АГЕНТ ---\\n{summary}"))
    
    return state
'''
        
    graph_def = GraphDefinition(
        nodes=[
            # Супер router
            GraphNode(
                id="super_router",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=super_router_code
            ),
            # Math flow нода
            GraphNode(
                id="math_flow",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=math_flow_code
            ),
            # Weather flow нода
            GraphNode(
                id="weather_flow",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=weather_flow_code
            ),
            # Finalizer нода
            GraphNode(
                id="finalizer",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=finalizer_code
            )
        ],
        edges=[
            # START → super_router
            GraphEdge(source="START", target="super_router"),
            # Conditional edges от super_router
            GraphEdge(
                source="super_router", 
                target="math_flow", 
                condition="super_router_condition",
                condition_type=ConditionType.ROUTER
            ),
            GraphEdge(
                source="super_router", 
                target="weather_flow", 
                condition="super_router_condition",
                condition_type=ConditionType.ROUTER
            ),
            # К finalizer
            GraphEdge(source="math_flow", target="finalizer"),
            GraphEdge(source="weather_flow", target="finalizer"),
            GraphEdge(source="finalizer", target="END")
        ],
        entry_point="START"
    )
        
    # 2. СОЗДАЕМ АГЕНТ КОНФИГУРАЦИЮ
    super_agent_config = AgentConfig(
        agent_id="super_flow_agent",
        name="Super Flow Agent",
        description="StateGraph агент который оркестрирует другие флоу",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        llm_config=LLMConfig(model="mock-gpt-4"),
        source="manual"
    )
        
    await agent_repo.set(super_agent_config)
    print("✅ Супер StateGraph агент создан в БД")
    
    # Создаем flow
    await test_helpers.create_simple_flow(
        flow_id="super_flow",
        name="Super Flow",
        entry_point_agent="super_flow_agent"
    )
    print("✅ Супер Flow создан в БД")
        
    return True

@pytest.mark.asyncio
async def test_execute_super_flow_math(migrated_db,  flow_factory, test_helpers, unique_id, agent_repo):
    """Создание и выполнение супер флоу с математическим запросом"""
    
    # Создаем агента
    await test_create_stategraph_with_flow_nodes(migrated_db,  test_helpers, agent_repo)
    
    super_flow = await flow_factory.get_flow("super_flow")
    
    result = await super_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 25 * 4")]},
        config={"configurable": {"session_id": unique_id("test_super_math")}}
    )
    
    assert "messages" in result
    
    final_message = result["messages"][-1].content
    assert "СУПЕР-АГЕНТ" in final_message
    # Проверяем что агент работает (получаем хоть какой-то результат)
    assert len(final_message) > 10
        
    print(f"✅ Супер флоу математический тест: {final_message}")

@pytest.mark.asyncio
async def test_execute_super_flow_weather(migrated_db,  flow_factory, test_helpers, unique_id, agent_repo):
    """Создание и выполнение супер флоу с погодным запросом"""
    
    # Создаем агента
    await test_create_stategraph_with_flow_nodes(migrated_db,  test_helpers, agent_repo)
    
    super_flow = await flow_factory.get_flow("super_flow")
    
    result = await super_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Екатеринбурге?")]},
        config={"configurable": {"session_id": unique_id("test_super_weather")}}
    )
    
    assert "messages" in result
    
    final_message = result["messages"][-1].content
    assert "СУПЕР-АГЕНТ" in final_message
    # Проверяем что агент работает (получаем хоть какой-то результат)
    assert len(final_message) > 10
        
    print(f"✅ Супер флоу погодный тест: {final_message}")

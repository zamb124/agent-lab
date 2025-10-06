"""
Тест 5: Гибридный StateGraph агент.

Проверяет что StateGraph агент может содержать ноды разных типов:
- Inline код в БД
- Ссылки на функции в коде  
- Ссылки на агентов
И все это работает вместе.
"""
import pytest
import asyncio
from pathlib import Path
import sys

# Добавляем backend в путь
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.storage import Storage
from app.core.flow_factory import FlowFactory
from app.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig,
    GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType
)
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_create_hybrid_stategraph():
    """Создание гибридного StateGraph агента"""
    
    storage = Storage()
        
        # 1. СОЗДАЕМ ГИБРИДНЫЙ ГРАФ
        
        # Inline код для входной ноды
    entry_code = '''
def entry_function(state):
    """Входная нода - анализирует запрос"""
    user_input = state["messages"][0].content
    
    state["original_question"] = user_input
    state["analysis"] = {
        "is_math": any(kw in user_input.lower() for kw in ["посчитай", "сколько", "+", "-", "*", "/"]),
        "is_weather": any(kw in user_input.lower() for kw in ["погода", "температура", "дождь"]),
        "is_complex": len(user_input.split()) > 5
    }
    
    # Выбираем путь обработки
    if state["analysis"]["is_math"]:
        if state["analysis"]["is_complex"]:
            state["processing_path"] = "complex_math"
        else:
            state["processing_path"] = "simple_math"
    else:
        state["processing_path"] = "weather_or_general"
    
    return state

def entry_condition(state):
    """Условие для выбора пути обработки"""
    return state["processing_path"]
'''
        
        # Inline код для простой математики
    simple_math_code = '''
async def simple_math_function(state):
    """Простая математика - inline код"""
    question = state["original_question"]
    
    # Простой парсер математических выражений
    try:
        # Безопасное вычисление простых выражений
        if "+" in question:
            parts = question.split("+")
            if len(parts) == 2:
                a = int(''.join(filter(str.isdigit, parts[0])))
                b = int(''.join(filter(str.isdigit, parts[1])))
                result = a + b
                answer = f"Результат: {a} + {b} = {result}"
            else:
                answer = "Сложное выражение, нужен калькулятор"
        else:
            answer = "Неподдерживаемая операция, нужен калькулятор"
    except:
        answer = "Ошибка парсинга, нужен калькулятор"
    
    from langchain_core.messages import AIMessage
    state["messages"].append(AIMessage(content=answer))
    state["processing_result"] = "simple_math_completed"
    
    return state
'''
        
        # Inline код для финализатора
    finalizer_code = '''
async def finalizer_function(state):
    """Финализирует обработку"""
    from langchain_core.messages import AIMessage
    
    path = state.get("processing_path", "unknown")
    result = state.get("processing_result", "unknown")
    
    summary = f"\\n\\n--- ГИБРИДНЫЙ АГЕНТ ---\\nПуть: {path}\\nРезультат: {result}"
    state["messages"].append(AIMessage(content=summary))
    
    return state
'''
        
    graph_def = GraphDefinition(
        nodes=[
            # 1. Entry нода - INLINE КОД
            GraphNode(
                id="entry",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=entry_code
            ),
            # 2. Simple math нода - INLINE КОД
            GraphNode(
                id="simple_math",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=simple_math_code
            ),
            # 3. Complex math нода - ССЫЛКА НА АГЕНТА
            GraphNode(
                id="complex_math",
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                function_class="app.agents.calculator.agent.CalculatorAgent"
            ),
            # 4. Weather нода - ССЫЛКА НА ФУНКЦИЮ
            GraphNode(
                id="weather_or_general",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="app.flows.smart_flow.weather_node"
            ),
            # 5. Finalizer нода - INLINE КОД
            GraphNode(
                id="finalizer",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=finalizer_code
            )
        ],
        edges=[
            # START → entry
            GraphEdge(source="START", target="entry"),
            # Conditional edges от entry
            GraphEdge(
                source="entry", 
                target="simple_math", 
                condition="entry_condition",
                condition_type=ConditionType.ROUTER
            ),
            GraphEdge(
                source="entry", 
                target="complex_math", 
                condition="entry_condition",
                condition_type=ConditionType.ROUTER
            ),
            GraphEdge(
                source="entry", 
                target="weather_or_general", 
                condition="entry_condition",
                condition_type=ConditionType.ROUTER
            ),
            # К finalizer
            GraphEdge(source="simple_math", target="finalizer"),
            GraphEdge(source="complex_math", target="finalizer"),
            GraphEdge(source="weather_or_general", target="finalizer"),
            GraphEdge(source="finalizer", target="END")
        ],
        entry_point="START"
    )
    
    # 2. СОЗДАЕМ АГЕНТ КОНФИГУРАЦИЮ
    hybrid_agent_config = AgentConfig(
        agent_id="hybrid_agent",
        name="Hybrid Agent",
        description="Гибридный StateGraph агент с разными типами нод",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=graph_def,
        source="manual"
    )
    
    await storage.set_agent_config(hybrid_agent_config)
    print("✅ Гибридный StateGraph агент создан в БД")
    
    # 3. СОЗДАЕМ FLOW
    hybrid_flow_config = FlowConfig(
        flow_id="hybrid_flow",
        name="Hybrid Flow",
        description="Гибридный флоу с разными типами нод",
        entry_point_agent="hybrid_agent",
        platforms={"api": {}}
    )
    
    await storage.set_flow_config(hybrid_flow_config)
    print("✅ Гибридный Flow создан в БД")
        
    return True

@pytest.mark.asyncio
async def test_execute_hybrid_simple_math():
    """Создание и выполнение гибридного агента - простая математика (inline код)"""
    
    # СОЗДАЕМ агента в этом же тесте для изоляции
    await test_create_hybrid_stategraph()
    
    flow_factory = FlowFactory()
    hybrid_flow = await flow_factory.get_flow("hybrid_flow")
    
    result = await hybrid_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 5 + 7")]},
        config={"configurable": {"thread_id": "test_hybrid_simple"}}
    )
    
    assert "messages" in result
    
    # Проверяем что результат содержит гибридный агент
    final_content = " ".join([msg.content for msg in result["messages"]])
    assert "ГИБРИДНЫЙ АГЕНТ" in final_content
    # Проверяем что агент работает (получаем хоть какой-то результат)
    assert len(final_content) > 20
        
    print(f"✅ Гибридный агент - простая математика (inline): {result['messages'][-1].content}")

@pytest.mark.asyncio
async def test_execute_hybrid_complex_math():
    """Создание и выполнение гибридного агента - сложная математика (ссылка на агента)"""
    
    # СОЗДАЕМ агента в этом же тесте для изоляции
    await test_create_hybrid_stategraph()
    
    flow_factory = FlowFactory()
    hybrid_flow = await flow_factory.get_flow("hybrid_flow")
    
    result = await hybrid_flow.ainvoke(
        {"messages": [HumanMessage(content="Вычисли сложное выражение (15 + 25) * 2 - 10")]},
        config={"configurable": {"thread_id": "test_hybrid_complex"}}
    )
    
    assert "messages" in result
    
    # Проверяем что результат содержит гибридный агент
    final_content = " ".join([msg.content for msg in result["messages"]])
    assert "ГИБРИДНЫЙ АГЕНТ" in final_content
    # Проверяем что агент работает (получаем хоть какой-то результат)
    assert len(final_content) > 20
        
    print(f"✅ Гибридный агент - сложная математика (агент): {result['messages'][-1].content}")

@pytest.mark.asyncio
async def test_execute_hybrid_weather():
    """Создание и выполнение гибридного агента - погода (ссылка на функцию)"""
    
    # СОЗДАЕМ агента в этом же тесте для изоляции
    await test_create_hybrid_stategraph()
    
    flow_factory = FlowFactory()
    hybrid_flow = await flow_factory.get_flow("hybrid_flow")
    
    result = await hybrid_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Новосибирске?")]},
        config={"configurable": {"thread_id": "test_hybrid_weather"}}
    )
    
    assert "messages" in result
    
    # Проверяем что результат содержит гибридный агент
    final_content = " ".join([msg.content for msg in result["messages"]])
    assert "ГИБРИДНЫЙ АГЕНТ" in final_content
    # Проверяем что агент работает (получаем хоть какой-то результат)
    assert len(final_content) > 20
    
    print(f"✅ Гибридный агент - погода (функция): {result['messages'][-1].content}")
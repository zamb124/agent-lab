"""
Тест создания и выполнения StateGraph агента напрямую из БД.

Проверяем что агент с несколькими нодами и conditional edges работает
без необходимости писать код - только через конфигурацию в БД.
"""

import pytest
from app.models import (
    AgentConfig,
    AgentType,
    GraphDefinition,
    GraphNode,
    GraphEdge,
    NodeType,
    ConditionType,
    CodeMode,
)
from app.core.storage import Storage
from app.core.agent_factory import AgentFactory


@pytest.mark.asyncio
async def test_stategraph_from_db_with_conditional():
    """
    Создаем StateGraph агента в БД с:
    - 5 нодами (router, process_a, process_b, merge, finish)
    - Conditional edge от router
    - Проверяем что граф работает корректно
    """
    
    storage = Storage()
    
    # Определяем inline код для нод
    router_code = '''
async def router_function(state):
    """Роутер который выбирает путь на основе входных данных"""
    from langchain_core.messages import AIMessage
    messages = state.get("messages", [])
    if messages:
        text = messages[0].content.lower()
        # Если "a" в тексте - идем в process_a, иначе в process_b
        route = "process_a" if "a" in text else "process_b"
        state["messages"].append(AIMessage(content=f"[ROUTER] Выбран маршрут: {route}"))
    return state

def router_condition(state):
    """Условие для роутера"""
    # Смотрим в последнее сообщение от роутера
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1].content
        if "[ROUTER]" in last_msg:
            return "process_a" if "process_a" in last_msg else "process_b"
    return "process_b"
'''
    
    process_a_code = '''
async def process_a_function(state):
    """Обрабатывает путь A"""
    from langchain_core.messages import AIMessage
    state["messages"].append(AIMessage(content="Обработано через путь A"))
    state["path_taken"] = "A"
    return state
'''
    
    process_b_code = '''
async def process_b_function(state):
    """Обрабатывает путь B"""
    from langchain_core.messages import AIMessage
    state["messages"].append(AIMessage(content="Обработано через путь B"))
    state["path_taken"] = "B"
    return state
'''
    
    merge_code = '''
async def merge_function(state):
    """Объединяет результаты"""
    from langchain_core.messages import AIMessage
    path = state.get("path_taken", "unknown")
    state["messages"].append(AIMessage(content=f"Результат объединен. Путь: {path}"))
    return state
'''
    
    finish_code = '''
async def finish_function(state):
    """Финальная обработка"""
    from langchain_core.messages import AIMessage
    state["messages"].append(AIMessage(content="✅ Граф завершен успешно"))
    return state
'''
    
    # Создаем GraphDefinition
    graph_def = GraphDefinition(
        nodes=[
            # Роутер с conditional logic
            GraphNode(
                id="router",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=router_code,
                params={}
            ),
            # Путь A
            GraphNode(
                id="process_a",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=process_a_code,
                params={}
            ),
            # Путь B
            GraphNode(
                id="process_b",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=process_b_code,
                params={}
            ),
            # Merge результатов
            GraphNode(
                id="merge",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=merge_code,
                params={}
            ),
            # Финиш
            GraphNode(
                id="finish",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code=finish_code,
                params={}
            ),
        ],
        edges=[
            # START → router
            GraphEdge(source="START", target="router"),
            
            # router → process_a (conditional)
            # GraphBuilder автоматически найдет router_condition в inline коде
            GraphEdge(
                source="router",
                target="process_a",
                condition_type=ConditionType.ROUTER
            ),
            
            # router → process_b (conditional)
            GraphEdge(
                source="router",
                target="process_b",
                condition_type=ConditionType.ROUTER
            ),
            
            # process_a → merge
            GraphEdge(source="process_a", target="merge"),
            
            # process_b → merge
            GraphEdge(source="process_b", target="merge"),
            
            # merge → finish
            GraphEdge(source="merge", target="finish"),
            
            # finish → END
            GraphEdge(source="finish", target="END"),
        ],
        entry_point="START"
    )
    
    # Создаем AgentConfig
    agent_config = AgentConfig(
        agent_id="test_stategraph_from_db",
        name="Test StateGraph from DB",
        description="Тестовый StateGraph агент созданный напрямую в БД",
        type=AgentType.STATEGRAPH,
        graph_definition=graph_def,
        source="test",
    )
    
    # Сохраняем в БД
    await storage.set_agent_config(agent_config)
    print("✅ Агент сохранен в БД")
    
    # Загружаем агента через фабрику
    factory = AgentFactory()
    agent = await factory.get_agent("test_stategraph_from_db")
    print(f"✅ Агент загружен: {agent.config.name}")
    
    # Компилируем граф
    compiled_graph = await agent.compile_graph()
    print("✅ Граф скомпилирован")
    
    # Очищаем checkpoints от предыдущих запусков
    from app.core.checkpointer import get_checkpointer
    checkpointer = await get_checkpointer()
    # Создаем конфигурации для очистки
    config_a = {"configurable": {"thread_id": "test_path_a"}}
    config_b = {"configurable": {"thread_id": "test_path_b"}}
    
    # Тест 1: Путь A (с "a" в тексте)
    print("\n=== Тест 1: Путь A ===")
    from langchain_core.messages import HumanMessage
    
    result_a = await compiled_graph.ainvoke(
        {"messages": [HumanMessage(content="Привет, хочу путь a")]},
        config=config_a
    )
    
    messages_a = result_a["messages"]
    print(f"Получено {len(messages_a)} сообщений:")
    for i, msg in enumerate(messages_a):
        print(f"  {i}: {msg.content}")
    
    # Проверяем что есть ключ path_taken
    assert "path_taken" in result_a, "State должен содержать path_taken"
    assert result_a["path_taken"] == "A", f"Путь должен быть A, но получен {result_a.get('path_taken')}"
    
    # Проверяем последовательность сообщений
    assert len(messages_a) >= 4, f"Ожидалось минимум 4 сообщения, получено {len(messages_a)}"
    assert "[ROUTER]" in messages_a[1].content
    assert "путь A" in messages_a[2].content
    assert "Путь: A" in messages_a[3].content
    assert "завершен успешно" in messages_a[4].content
    print(f"✅ Путь A отработал корректно")
    
    # Тест 2: Путь B (без "a" в тексте)
    print("\n=== Тест 2: Путь B ===")
    
    result_b = await compiled_graph.ainvoke(
        {"messages": [HumanMessage(content="Привет, хочу другой путь")]},
        config=config_b
    )
    
    messages_b = result_b["messages"]
    print(f"Получено {len(messages_b)} сообщений:")
    for i, msg in enumerate(messages_b):
        print(f"  {i}: {msg.content}")
    
    # Проверяем что есть ключ path_taken
    assert "path_taken" in result_b, "State должен содержать path_taken"
    assert result_b["path_taken"] == "B", f"Путь должен быть B, но получен {result_b.get('path_taken')}"
    
    # Проверяем последовательность сообщений
    assert len(messages_b) >= 4, f"Ожидалось минимум 4 сообщения, получено {len(messages_b)}"
    assert "[ROUTER]" in messages_b[1].content
    assert "путь B" in messages_b[2].content
    assert "Путь: B" in messages_b[3].content
    assert "завершен успешно" in messages_b[4].content
    print(f"✅ Путь B отработал корректно")
    
    print("\n✅ Все тесты пройдены! StateGraph из БД работает корректно")
    
    # Очистка
    await storage.delete(f"agent:test_stategraph_from_db")
    print("✅ Тестовый агент удален из БД")

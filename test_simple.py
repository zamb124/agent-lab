#!/usr/bin/env python3
"""
ПРОСТЕЙШИЙ тест передачи state между функциями
"""
import asyncio
from langgraph.graph import StateGraph
from typing import Dict, Any, List
from langchain_core.messages import BaseMessage

# Простой GraphState
class SimpleState(Dict[str, Any]):
    messages: List[BaseMessage]

def func1(state):
    """Первая функция - добавляет данные в state"""
    print(f"🔍 FUNC1 получила state: {list(state.keys())}")
    print(f"🔍 FUNC1 state: {state}")
    
    # Обновляем state
    state["data_from_func1"] = "Привет от func1!"
    
    print(f"🔍 FUNC1 обновила state: {list(state.keys())}")
    return state

def func2(state):
    """Вторая функция - читает данные от первой"""
    print(f"🔍 FUNC2 получила state: {list(state.keys())}")
    print(f"🔍 FUNC2 state: {state}")
    
    data_from_func1 = state.get("data_from_func1", "НЕТ ДАННЫХ!")
    print(f"🔍 FUNC2 прочитала от FUNC1: {data_from_func1}")
    
    return {"result": f"Получено: {data_from_func1}"}

async def test_simple_state():
    """Тестирует простую передачу state"""
    
    # Создаем простой граф
    graph = StateGraph(SimpleState)
    
    graph.add_node("func1", func1)
    graph.add_node("func2", func2)
    
    graph.set_entry_point("func1")
    graph.add_edge("func1", "func2")
    
    compiled = graph.compile()
    
    initial_state = {"messages": [], "test": "начальные данные"}
    
    print("🧪 ПРОСТЕЙШИЙ ТЕСТ")
    print(f"📤 Initial: {initial_state}")
    
    result = await compiled.ainvoke(initial_state)
    
    print(f"📥 Final: {result}")

if __name__ == "__main__":
    asyncio.run(test_simple_state())

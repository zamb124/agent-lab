"""
Test Flow - простой флоу без LLM для тестирования интерфейсов.
"""
from typing import TypedDict, List
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from app.agents.base import BaseAgent
from app.core.models import FlowConfig


class TestState(TypedDict):
    messages: List[BaseMessage]


async def test_response_node(state: TestState) -> TestState:
    """Простая нода которая возвращает ОК"""
    user_message = state["messages"][0].content if state["messages"] else "неизвестно"
    
    response = AIMessage(content=f"✅ ОК! Получил сообщение: '{user_message}'")
    state["messages"].append(response)
    
    return state


class TestFlowAgent(BaseAgent):
    """Простой StateGraph агент без LLM для тестирования"""
    
    name = "Test Flow Agent"
    description = "Простой агент для тестирования интерфейсов"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Создаем простой граф
        self.graph = StateGraph(TestState)
        
        # Добавляем единственную ноду
        self.graph.add_node("test_response", test_response_node)
        
        # Простой маршрут: START → test_response → END
        self.graph.set_entry_point("test_response")
        self.graph.add_edge("test_response", END)
        
        # Компилируем граф БЕЗ checkpointer (не нужен для простого теста)
        self.compiled_graph = self.graph.compile()
    
    async def ainvoke(self, input_data, config=None):
        """Стандартный LangGraph ainvoke"""
        return await self.compiled_graph.ainvoke(input_data, config)


# Test Flow конфигурация
test_flow_config = FlowConfig(
    flow_id="test_flow",
    name="Test Flow",
    description="Простой тестовый флоу без LLM",
    entry_point_agent="app.flows.test_flow.TestFlowAgent",
    platforms={
        "api": {},
        "telegram": {
            "username": "agents_lab_bot"
        }
    }
)

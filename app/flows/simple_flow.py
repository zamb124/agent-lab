"""
Test Flow - простой флоу без LLM для тестирования интерфейсов.
"""

from typing import TypedDict, List
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.agents.stategraph_agent import StateGraphAgent
from app.models import FlowConfig


class TestState(TypedDict):
    messages: List[BaseMessage]


async def test_response_node(state: TestState) -> TestState:
    """Простая нода которая возвращает ОК"""
    user_message = state["messages"][0].content if state["messages"] else "неизвестно"

    response = AIMessage(content=f"✅ ОК! Получил сообщение: '{user_message}'")
    state["messages"].append(response)

    return state


class SimpleFlowAgent(StateGraphAgent):
    """Простой StateGraph агент без LLM для тестирования"""

    name = "Test Flow Agent"
    description = "Простой агент для тестирования интерфейсов"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph = self.build_graph()
        self.compiled_graph = self.graph.compile()

    def build_graph(self):
        """Создает и возвращает граф"""
        graph = StateGraph(TestState)
        
        graph.add_node("test_response", test_response_node)
        
        graph.set_entry_point("test_response")
        graph.add_edge("test_response", END)
        
        return graph

    async def ainvoke(self, input_data, config=None):
        """Стандартный LangGraph ainvoke"""
        return await self.compiled_graph.ainvoke(input_data, config)


# Test Flow конфигурация
simple_flow_config = FlowConfig(
    name="Test Flow",
    description="Простой тестовый флоу без LLM",
    entry_point_agent="app.flows.simple_flow.SimpleFlowAgent",
    platforms={"api": {}, "telegram": {"username": "agents_lab_bot"}},
    is_public=True,
)

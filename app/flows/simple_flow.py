"""
Test Flow - простой флоу без LLM для тестирования интерфейсов.
"""

from typing import Dict, Any
from langchain_core.messages import AIMessage
from app.core.state import State

from app.agents.stategraph_agent import StateGraphAgent
from app.models import FlowConfig, NodeType, ConditionType, CodeMode


async def test_response_node(state: State) -> State:
    """Простая нода которая возвращает ОК"""
    messages = state.get("messages", [])
    user_message = messages[0].content if messages else "неизвестно"

    response = AIMessage(content=f"✅ ОК! Получил сообщение: '{user_message}'")
    state["messages"] = messages + [response]

    return state


class SimpleFlowAgent(StateGraphAgent):
    """Простой StateGraph агент без LLM для тестирования"""

    name = "Test Flow Agent"
    description = "Простой агент для тестирования интерфейсов"

    def graph_definition(self) -> Dict[str, Any]:
        """Определение графа для StateGraphRunner"""
        return {
            "entry_point": "test_response",
            "nodes": [
                {
                    "id": "test_response",
                    "type": NodeType.FUNCTION_NODE,
                    "code_mode": CodeMode.CODE_REFERENCE,
                    "function_path": "app.flows.simple_flow.test_response_node",
                },
            ],
            "edges": [
                {
                    "source": "START",
                    "target": "test_response",
                },
                {
                    "source": "test_response",
                    "target": "END",
                },
            ],
        }


# Test Flow конфигурация
simple_flow_config = FlowConfig(
    name="Test Flow",
    description="Простой тестовый флоу без LLM",
    entry_point_agent="app.flows.simple_flow.SimpleFlowAgent",
    platforms={"api": {}, "telegram": {"username": "agents_lab_bot"}},
    is_public=True,
)

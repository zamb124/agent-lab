"""
Smart Flow - флоу с роутером, калькулятором, погодой и объяснениями.
Переписан без LangGraph, использует StateGraphRunner.
"""

from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage
from app.agents.stategraph_agent import StateGraphAgent
from app.models import FlowConfig, GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType, CodeMode
from app.core.container import get_container
from app.core.state import State


async def router_node(state: State) -> State:
    """Анализирует запрос и обновляет state"""
    messages = state.get("messages", [])
    if not messages:
        return state
    
    last_message = messages[-1]
    user_input = last_message.content if hasattr(last_message, "content") else str(last_message)

    # Сохраняем исходный вопрос
    if "store" not in state:
        state["store"] = {}
    state["store"]["original_question"] = user_input

    # Выбираем агента
    if any(
        kw in user_input.lower() for kw in ["посчитай", "сколько", "+", "-", "*", "/"]
    ):
        state["store"]["selected_agent"] = "calculator"
    else:
        state["store"]["selected_agent"] = "weather"

    return state


def router_condition(state: State) -> str:
    """Условие для выбора следующего агента"""
    selected_agent = state.get("store", {}).get("selected_agent", "weather")
    return selected_agent


async def calculator_node(state: State) -> State:
    """Вызов калькулятора"""
    factory = get_container().agent_factory
    calculator = await factory.get_agent("app.agents.calculator.agent.CalculatorAgent")
    original_question = state.get("store", {}).get("original_question", "")
    result = await calculator.ainvoke({
        "messages": [HumanMessage(content=original_question)]
    })
    state["messages"] = result.get("messages", [])
    return state


async def weather_node(state: State) -> State:
    """Вызов погодного агента"""
    factory = get_container().agent_factory
    weather = await factory.get_agent("app.agents.weather.agent.WeatherAgent")
    result = await weather.ainvoke({"messages": state.get("messages", [])})
    state["messages"] = result.get("messages", [])
    return state


async def explainer_node(state: State) -> State:
    """Вызов объяснителя"""
    factory = get_container().agent_factory
    explainer = await factory.get_agent("app.agents.explainer.agent.ExplainerAgent")

    store = state.get("store", {})
    original_q = store.get("original_question", "")
    selected_agent = store.get("selected_agent", "weather")
    
    agent_type = "калькулятор" if selected_agent == "calculator" else "погодный"
    messages = state.get("messages", [])
    agent_result = messages[-1].content if messages and hasattr(messages[-1], "content") else "нет результата"

    explainer_input = f"""
Исходный вопрос пользователя: "{original_q}"
Выбранный агент: {agent_type}
Результат работы агента: "{agent_result}"

Объясни что произошло и дай резюме.
    """.strip()

    result = await explainer.ainvoke({
        "messages": [HumanMessage(content=explainer_input)]
    })

    state["messages"] = result.get("messages", [])
    return state


class SmartFlowAgent(StateGraphAgent):
    """StateGraph агент - переписан без LangGraph, использует StateGraphRunner"""

    name = "Smart Flow Agent"
    description = "StateGraph агент с роутингом между калькулятором и погодой"

    def graph_definition(self) -> Dict[str, Any]:
        """Определение графа для StateGraphRunner"""
        return {
            "entry_point": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": NodeType.FUNCTION_NODE,
                    "code_mode": CodeMode.CODE_REFERENCE,
                    "function_path": "app.flows.smart_flow.router_node",
                },
                {
                    "id": "calculator",
                    "type": NodeType.FUNCTION_NODE,
                    "code_mode": CodeMode.CODE_REFERENCE,
                    "function_path": "app.flows.smart_flow.calculator_node",
                },
                {
                    "id": "weather",
                    "type": NodeType.FUNCTION_NODE,
                    "code_mode": CodeMode.CODE_REFERENCE,
                    "function_path": "app.flows.smart_flow.weather_node",
                },
                {
                    "id": "explainer",
                    "type": NodeType.FUNCTION_NODE,
                    "code_mode": CodeMode.CODE_REFERENCE,
                    "function_path": "app.flows.smart_flow.explainer_node",
                },
            ],
            "edges": [
                {
                    "source": "START",
                    "target": "router",
                },
                {
                    "source": "router",
                    "target": "calculator",
                    "condition_type": ConditionType.ROUTER,
                    "condition": "app.flows.smart_flow.router_condition",
                },
                {
                    "source": "router",
                    "target": "weather",
                    "condition_type": ConditionType.ROUTER,
                    "condition": "app.flows.smart_flow.router_condition",
                },
                {
                    "source": "calculator",
                    "target": "explainer",
                },
                {
                    "source": "weather",
                    "target": "explainer",
                },
                {
                    "source": "explainer",
                    "target": "END",
                },
            ],
        }


# Smart Flow конфигурация
smart_flow_config = FlowConfig(
    name="Smart Flow",
    description="Умный флоу с роутингом между калькулятором и погодой",
    entry_point_agent="app.flows.smart_flow.SmartFlowAgent",
    platforms={"api": {}, "telegram": {}},
)

"""
Smart Flow - флоу с роутером, калькулятором, погодой и объяснениями.
"""

from typing import TypedDict, List
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from app.agents.base import BaseAgent
from app.models import FlowConfig
from app.core.agent_factory import AgentFactory


class RouterState(TypedDict):
    messages: List[BaseMessage]
    original_question: str
    selected_agent: str


def router_function(state: RouterState) -> RouterState:
    """Анализирует запрос и обновляет state"""
    user_input = state["messages"][0].content

    # Сохраняем исходный вопрос
    state["original_question"] = user_input

    # Выбираем агента
    if any(
        kw in user_input.lower() for kw in ["посчитай", "сколько", "+", "-", "*", "/"]
    ):
        state["selected_agent"] = "calculator"
    else:
        state["selected_agent"] = "weather"

    return state


def router_condition(state: RouterState) -> str:
    """Условие для выбора следующего агента"""
    return state["selected_agent"]


async def calculator_node(state: RouterState) -> RouterState:
    """Вызов калькулятора"""
    factory = AgentFactory()
    calculator = await factory.get_agent("app.agents.calculator.agent.CalculatorAgent")
    result = await calculator.ainvoke(
        {"messages": [{"role": "user", "content": state["original_question"]}]}
    )
    state["messages"] = result["messages"]
    return state


async def weather_node(state: RouterState) -> RouterState:
    """Вызов погодного агента"""
    factory = AgentFactory()
    weather = await factory.get_agent("app.agents.weather.agent.WeatherAgent")
    result = await weather.ainvoke({"messages": state["messages"]})
    state["messages"] = result["messages"]
    return state


async def explainer_node(state: RouterState) -> RouterState:
    """Вызов объяснителя"""
    factory = AgentFactory()
    explainer = await factory.get_agent("app.agents.explainer.agent.ExplainerAgent")

    # Формируем правильный запрос для ExplainerAgent
    original_q = state["original_question"]
    agent_type = (
        "калькулятор" if state["selected_agent"] == "calculator" else "погодный"
    )
    agent_result = (
        state["messages"][-1].content if state["messages"] else "нет результата"
    )

    explainer_input = f"""
Исходный вопрос пользователя: "{original_q}"
Выбранный агент: {agent_type}
Результат работы агента: "{agent_result}"

Объясни что произошло и дай резюме.
    """.strip()

    result = await explainer.ainvoke(
        {"messages": [HumanMessage(content=explainer_input)]}
    )

    state["messages"] = result["messages"]
    return state


class SmartFlowAgent(BaseAgent):
    """StateGraph агент - наследник BaseAgent с чистым LangGraph кодом"""

    name = "Smart Flow Agent"
    description = "StateGraph агент с роутингом между калькулятором и погодой"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph = self.build_graph()
        self.compiled_graph = None

    def build_graph(self):
        """Создает и возвращает граф"""
        graph = StateGraph(RouterState)

        graph.add_node("router", router_function)
        graph.add_node("calculator", calculator_node)
        graph.add_node("weather", weather_node)
        graph.add_node("explainer", explainer_node)

        graph.add_edge(START, "router")

        graph.add_conditional_edges(
            "router",
            router_condition,
            {"calculator": "calculator", "weather": "weather"},
        )

        graph.add_edge("calculator", "explainer")
        graph.add_edge("weather", "explainer")
        graph.add_edge("explainer", END)

        return graph

    async def ainvoke(self, input_data, config=None):
        """Стандартный LangGraph ainvoke"""
        if self.compiled_graph is None:
            from app.core.checkpointer import get_checkpointer
            checkpointer = await get_checkpointer()
            self.compiled_graph = self.graph.compile(checkpointer=checkpointer)
        
        return await self.compiled_graph.ainvoke(input_data, config)


# Smart Flow конфигурация
smart_flow_config = FlowConfig(
    name="Smart Flow",
    description="Умный флоу с роутингом между калькулятором и погодой",
    entry_point_agent="app.flows.smart_flow.SmartFlowAgent",
    platforms={"api": {}, "telegram": {}},
)

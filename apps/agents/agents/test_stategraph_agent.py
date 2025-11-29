"""
Тестовый StateGraph агент, демонстрирующий все типы нод.

Этот агент показывает как использовать:
- AGENT_NODE: вызов субагента
- TOOL_NODE: вызов инструмента
- FUNCTION_NODE: вызов функции
- MESSAGE_NODE: отправка сообщения
- FLOW_NODE: вызов другого flow
"""

import logging
from apps.agents.models import (
    AgentConfig,
    GraphDefinition,
    GraphNode,
    GraphEdge,
    NodeType,
    CodeMode,
    ConditionType,
)
from apps.agents.services.state import State

logger = logging.getLogger(__name__)


def greeting_function(state: State) -> State:
    """Функция приветствия"""
    logger.info("🎯 FUNCTION_NODE: greeting_function вызвана")
    
    if "store" not in state:
        state["store"] = {}
    
    state["store"]["greeting_done"] = True
    state["store"]["function_result"] = "Приветствие выполнено"
    
    return state


def process_data_function(state: State) -> State:
    """Функция обработки данных"""
    logger.info("🎯 FUNCTION_NODE: process_data_function вызвана")
    
    if "store" not in state:
        state["store"] = {}
    
    state["store"]["data_processed"] = True
    state["store"]["processing_result"] = "Данные обработаны успешно"
    
    return state


def router_function(state: State) -> str:
    """Функция роутинга для условных переходов"""
    logger.info("🎯 CONDITIONAL: router_function вызвана")
    
    store = state.get("store", {})
    
    if store.get("greeting_done"):
        logger.info("✅ Переход к process_data")
        return "process_data"
    else:
        logger.info("⚠️ Переход к END")
        return "END"


def final_function(state: State) -> State:
    """Финальная функция"""
    logger.info("🎯 FUNCTION_NODE: final_function вызвана")
    
    if "store" not in state:
        state["store"] = {}
    
    state["store"]["completed"] = True
    state["store"]["final_message"] = "Все этапы выполнены успешно!"
    
    return state


test_stategraph_agent_config = AgentConfig(
    agent_id="apps.agents.agents.test_stategraph_agent.test_stategraph_agent_config",
    name="Test StateGraph Agent",
    description="Демонстрационный агент со всеми типами нод",
    prompt="""Ты тестовый агент, который демонстрирует все возможности StateGraph.
    
У тебя есть доступ к различным субагентам и инструментам.
Ты можешь выполнять сложные сценарии с условными переходами.""",
    
    graph_definition=GraphDefinition(
        nodes=[
            # 1. MESSAGE_NODE - отправка приветствия
            GraphNode(
                id="welcome_message",
                type=NodeType.MESSAGE_NODE,
                params={
                    "message": "🎉 Добро пожаловать в тестовый StateGraph агент! Начинаем демонстрацию всех типов нод."
                },
                code_mode=CodeMode.CODE_REFERENCE,
            ),
            
            # 2. FUNCTION_NODE - функция приветствия
            GraphNode(
                id="greeting",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="apps.agents.agents.test_stategraph_agent.greeting_function",
                params={
                    "description": "Выполняет приветствие и устанавливает флаг"
                }
            ),
            
            # 3. AGENT_NODE - вызов калькулятора (если есть)
            GraphNode(
                id="calculator_agent",
                type=NodeType.AGENT_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                params={
                    "agent_id": "apps.agents.agents.calculator.agent.CalculatorAgent",
                    "description": "Вызов субагента калькулятора"
                }
            ),
            
            # 4. TOOL_NODE - вызов инструмента
            GraphNode(
                id="calculator_tool",
                type=NodeType.TOOL_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                params={
                    "tool_id": "apps.agents.tools.calc.calc_tools.calculate",
                    "args": {"expression": "2+2"},
                    "output_key": "tool_result",
                    "description": "Вызов tool калькулятора"
                }
            ),
            
            # 5. FUNCTION_NODE с INLINE_CODE
            GraphNode(
                id="inline_function",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code="""
async def inline_function(state):
    '''Инлайн функция для демонстрации'''
    import logging
    logger = logging.getLogger(__name__)
    logger.info("🎯 INLINE FUNCTION_NODE: выполняется")
    
    if "store" not in state:
        state["store"] = {}
    
    state["store"]["inline_executed"] = True
    state["store"]["inline_result"] = "Инлайн код выполнен успешно"
    
    return state
""",
                params={
                    "description": "Инлайн функция из БД"
                }
            ),
            
            # 6. ROUTER_NODE - условная логика (определяет следующую ноду)
            GraphNode(
                id="router",
                type=NodeType.ROUTER_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code="""
def router_condition(state):
    '''Функция-роутер, определяет следующую ноду'''
    import logging
    logger = logging.getLogger(__name__)
    
    store = state.get("store", {})
    
    if store.get("inline_executed"):
        logger.info("✅ Router: переход к process_data")
        return "process_data"
    else:
        logger.info("⚠️ Router: переход к message_info")
        return "message_info"
""",
                params={
                    "description": "Роутер для условных переходов"
                }
            ),
            
            # 7. MESSAGE_NODE для информационного сообщения
            GraphNode(
                id="message_info",
                type=NodeType.MESSAGE_NODE,
                params={
                    "message": "ℹ️ Промежуточное информационное сообщение от MESSAGE_NODE"
                },
                code_mode=CodeMode.CODE_REFERENCE,
            ),
            
            # 8. FUNCTION_NODE - обработка данных
            GraphNode(
                id="process_data",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="apps.agents.agents.test_stategraph_agent.process_data_function",
                params={
                    "description": "Обработка данных"
                }
            ),
            
            # 9. FUNCTION_NODE - проверка условия (для EXPRESSION)
            GraphNode(
                id="check_condition",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.INLINE_CODE,
                inline_code="""
async def check_condition(state):
    '''Проверяет условие и устанавливает флаг'''
    import logging
    logger = logging.getLogger(__name__)
    logger.info("🎯 check_condition: проверяем условие")
    
    if "store" not in state:
        state["store"] = {}
    
    # Устанавливаем флаг для демонстрации EXPRESSION
    state["store"]["condition_passed"] = True
    
    return state
""",
                params={
                    "description": "Проверка условия для EXPRESSION edge"
                }
            ),
            
            # 10. FUNCTION_NODE - финальная функция
            GraphNode(
                id="final",
                type=NodeType.FUNCTION_NODE,
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="apps.agents.agents.test_stategraph_agent.final_function",
                params={
                    "description": "Финализация"
                }
            ),
        ],
        
        edges=[
            # START -> welcome_message
            GraphEdge(
                source="START",
                target="welcome_message"
            ),
            
            # welcome_message -> greeting
            GraphEdge(
                source="welcome_message",
                target="greeting"
            ),
            
            # greeting -> calculator_agent
            GraphEdge(
                source="greeting",
                target="calculator_agent"
            ),
            
            # calculator_agent -> calculator_tool
            GraphEdge(
                source="calculator_agent",
                target="calculator_tool"
            ),
            
            # calculator_tool -> inline_function
            GraphEdge(
                source="calculator_tool",
                target="inline_function"
            ),
            
            # inline_function -> router (conditional)
            GraphEdge(
                source="inline_function",
                target="router"
            ),
            
            # router -> process_data (conditional edge)
            GraphEdge(
                source="router",
                target="process_data",
                condition="apps.agents.agents.test_stategraph_agent.router_condition",
                condition_type=ConditionType.ROUTER
            ),
            
            # router -> message_info (conditional edge)
            GraphEdge(
                source="router",
                target="message_info",
                condition="apps.agents.agents.test_stategraph_agent.router_condition",
                condition_type=ConditionType.ROUTER
            ),
            
            # message_info -> process_data
            GraphEdge(
                source="message_info",
                target="process_data"
            ),
            
            # process_data -> check_condition
            GraphEdge(
                source="process_data",
                target="check_condition"
            ),
            
            # check_condition -> final (с EXPRESSION условием)
            # EXPRESSION: простое условие true/false на основе state
            GraphEdge(
                source="check_condition",
                target="final",
                condition="'store' in state and 'condition_passed' in state['store'] and state['store']['condition_passed']",
                condition_type=ConditionType.EXPRESSION
            ),
            
            # final -> END
            GraphEdge(
                source="final",
                target="END"
            ),
        ],
        
        entry_point="welcome_message"
    )
)


# Экспортируем для миграции
__all__ = [
    "test_stategraph_agent_config",
    "greeting_function",
    "process_data_function",
    "router_function",
    "final_function",
]


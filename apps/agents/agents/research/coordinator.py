"""
ResearchCoordinatorAgent - координатор процесса исследования.

Оркестрирует весь pipeline через StateGraph с условными переходами.
Использует декларативный graph_definition (через GraphBuilder).
"""

import logging
from langchain_core.messages import AIMessage
from apps.agents.agents.stategraph_agent import StateGraphAgent
from apps.agents.services.state import State
from apps.agents.models.core_models import GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType

logger = logging.getLogger(__name__)


async def return_final_report(state: State) -> State:
    """
    Финальная функция: возвращает готовый отчет пользователю.
    
    Берет финальный отчет из store и добавляет его как AIMessage в messages.
    Система автоматически отправит его пользователю.
    """
    store = state.get("store", {})
    final_report = store.get("final_report", "")
    
    if not final_report:
        logger.warning("Финальный отчет не найден в store!")
        final_report = "❌ Ошибка: финальный отчет не был создан"
    
    # Добавляем отчет в messages - система автоматически отправит его
    if "messages" not in state:
        state["messages"] = []
    state["messages"].append(AIMessage(content=final_report))
    
    logger.info(f"✅ Финальный отчет добавлен в messages ({len(final_report)} символов)")
    
    return state


def check_quality_decision(state: State) -> str:
    """
    Условная функция для router: определяет следующий шаг после проверки качества.
    
    Args:
        state: Текущий state с накопленными данными
        
    Returns:
        "search" если нужен дополнительный поиск
        "END" если исследование завершено
    """
    store = state.get("store", {})
    decision = store.get("quality_decision", "complete")
    
    logger.info(f"🔍 Quality decision: {decision}")
    
    if decision == "need_more_search":
        iteration = store.get("iteration", 0) + 1
        max_iterations = store.get("max_iterations", 2)
        
        if iteration >= max_iterations:
            logger.warning(
                f"Достигнут лимит итераций ({max_iterations}), "
                f"завершаем несмотря на низкое качество"
            )
            return "return_report"
        
        store["iteration"] = iteration
        logger.info(f"Запускаем дополнительную итерацию поиска ({iteration}/{max_iterations})")
        return "search"
    
    logger.info("Исследование завершено успешно")
    return "return_report"


class ResearchCoordinatorAgent(StateGraphAgent):
    """
    Координатор полного цикла исследования.
    
    Управляет последовательным выполнением всех этапов:
    1. QueryAnalyzer - анализ запроса
    2. SearchAgent - поиск информации
    3. SourceProcessor - обработка источников
    4. FactExtractor - извлечение фактов
    5. Synthesizer - синтез отчета
    6. QualityChecker - проверка качества
    7. Цикл: если качество низкое - возврат к поиску
    
    Использует StateGraph для гибкого управления потоком.
    Все данные накапливаются в state.store и персистятся автоматически.
    
    Переиспользуемый компонент: граф можно настроить через graph_definition,
    добавить/убрать этапы, изменить условия переходов.
    """
    
    name = "research_coordinator"
    title = "Координатор исследований"
    description = "Оркестрирует полный цикл исследования от запроса до отчета"
    is_public = True
    
    # Декларативное описание графа (GraphBuilder автоматически построит его)
    graph_definition = GraphDefinition(
        nodes=[
            GraphNode(
                id="analyze",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent"},
                description="Анализ запроса и создание подвопросов"
            ),
            GraphNode(
                id="search",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "apps.agents.agents.research.search_agent.SearchAgent"},
                description="Поиск информации по подвопросам"
            ),
            GraphNode(
                id="process",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "apps.agents.agents.research.source_processor.SourceProcessorAgent"},
                description="Обработка и фильтрация источников"
            ),
            GraphNode(
                id="extract",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "apps.agents.agents.research.fact_extractor.FactExtractorAgent"},
                description="Извлечение структурированных фактов"
            ),
            GraphNode(
                id="synthesize",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "apps.agents.agents.research.synthesizer.SynthesizerAgent"},
                description="Синтез финального отчета"
            ),
            GraphNode(
                id="check",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "apps.agents.agents.research.quality_checker.QualityCheckerAgent"},
                description="Проверка качества и принятие решения"
            ),
            GraphNode(
                id="return_report",
                type=NodeType.FUNCTION_NODE,
                params={"function": "apps.agents.agents.research.coordinator.return_final_report"},
                description="Возвращает финальный отчет пользователю"
            ),
        ],
        edges=[
            GraphEdge(source="START", target="analyze"),
            GraphEdge(source="analyze", target="search"),
            GraphEdge(source="search", target="process"),
            GraphEdge(source="process", target="extract"),
            GraphEdge(source="extract", target="synthesize"),
            GraphEdge(source="synthesize", target="check"),
            
            # Условный переход после проверки качества
            GraphEdge(
                source="check",
                target="search",
                condition_type=ConditionType.ROUTER,
                condition="apps.agents.agents.research.coordinator.check_quality_decision"
            ),
            GraphEdge(
                source="check",
                target="return_report",
                condition_type=ConditionType.ROUTER,
                condition="apps.agents.agents.research.coordinator.check_quality_decision"
            ),
            
            # Возврат финального отчета пользователю
            GraphEdge(source="return_report", target="END"),
        ],
        entry_point="analyze"
    )


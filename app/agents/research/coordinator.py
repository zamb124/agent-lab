"""
ResearchCoordinatorAgent - координатор процесса исследования.

Оркестрирует весь pipeline через StateGraph с условными переходами.
Использует декларативный graph_definition (через GraphBuilder).
"""

import logging
from app.agents.stategraph_agent import StateGraphAgent
from app.core.state import State
from app.models.core_models import GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType

logger = logging.getLogger(__name__)


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
            return "END"
        
        store["iteration"] = iteration
        logger.info(f"Запускаем дополнительную итерацию поиска ({iteration}/{max_iterations})")
        return "search"
    
    logger.info("Исследование завершено успешно")
    return "END"


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
                params={"agent_id": "app.agents.research.query_analyzer.QueryAnalyzerAgent"},
                description="Анализ запроса и создание подвопросов"
            ),
            GraphNode(
                id="search",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.search_agent.SearchAgent"},
                description="Поиск информации по подвопросам"
            ),
            GraphNode(
                id="process",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.source_processor.SourceProcessorAgent"},
                description="Обработка и фильтрация источников"
            ),
            GraphNode(
                id="extract",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.fact_extractor.FactExtractorAgent"},
                description="Извлечение структурированных фактов"
            ),
            GraphNode(
                id="synthesize",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.synthesizer.SynthesizerAgent"},
                description="Синтез финального отчета"
            ),
            GraphNode(
                id="check",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.quality_checker.QualityCheckerAgent"},
                description="Проверка качества и принятие решения"
            ),
        ],
        edges=[
            GraphEdge(source="START", target="analyze"),
            GraphEdge(source="analyze", target="search"),
            GraphEdge(source="search", target="process"),
            GraphEdge(source="process", target="extract"),
            GraphEdge(source="extract", target="synthesize"),
            GraphEdge(source="synthesize", target="check"),
            
            # Условный переход: если качество низкое - возврат к поиску
            GraphEdge(
                source="check",
                target="search",
                condition_type=ConditionType.ROUTER,
                condition="app.agents.research.coordinator.check_quality_decision"
            ),
            
            # Завершение если качество достаточное
            GraphEdge(source="check", target="END"),
        ],
        entry_point="analyze"
    )


"""
Research агенты для глубоких исследований.

Модульная система для проведения структурированных исследований
с использованием поиска, анализа и синтеза информации.
"""

from .query_analyzer import QueryAnalyzerAgent
from .search_agent import SearchAgent
from .source_processor import SourceProcessorAgent
from .fact_extractor import FactExtractorAgent
from .synthesizer import SynthesizerAgent
from .quality_checker import QualityCheckerAgent
from .coordinator import ResearchCoordinatorAgent

__all__ = [
    "QueryAnalyzerAgent",
    "SearchAgent",
    "SourceProcessorAgent",
    "FactExtractorAgent",
    "SynthesizerAgent",
    "QualityCheckerAgent",
    "ResearchCoordinatorAgent",
]


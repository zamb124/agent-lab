"""
Инструменты для анализа текста и обработки данных.

Категория: Analysis
Включает инструменты для анализа текста, извлечения фактов,
структурирования данных и синтеза информации.
"""

from .text_analysis import analyze_text, extract_key_points, summarize_text
from .fact_extraction import extract_facts, verify_facts, structure_facts
from .synthesis import synthesize_report, format_markdown, create_citations

__all__ = [
    "analyze_text",
    "extract_key_points",
    "summarize_text",
    "extract_facts",
    "verify_facts",
    "structure_facts",
    "synthesize_report",
    "format_markdown",
    "create_citations",
]


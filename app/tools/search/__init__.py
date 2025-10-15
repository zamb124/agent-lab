"""
Инструменты для поиска информации в интернете.

Категория: Search
Включает инструменты для работы с поисковыми API (Tavily, Serper),
извлечения контента с веб-страниц и обработки результатов поиска.
"""

from .tavily_search import tavily_search, tavily_search_advanced
from .serper_search import serper_search, serper_news_search
from .web_extract import extract_web_content, extract_metadata

__all__ = [
    "tavily_search",
    "tavily_search_advanced",
    "serper_search",
    "serper_news_search",
    "extract_web_content",
    "extract_metadata",
]


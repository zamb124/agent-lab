"""
Research Agent - агент для глубоких исследований через SGR Deep Research.

Этот агент является оберткой над микросервисом SGR Deep Research,
который использует Schema-Guided Reasoning для структурированных исследований.
"""

import logging
from typing import Optional

from app.agents.base import BaseAgent
from app.clients.sgr_client import SGRClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Агент для глубоких веб-исследований через SGR Deep Research микросервис.
    
    Использует SGR (Schema-Guided Reasoning) для:
    - Структурированного поиска информации в интернете
    - Анализа и синтеза данных из множества источников
    - Генерации детальных отчетов с цитированием
    
    Особенности:
    - Работает как микросервис (отдельный процесс)
    - Поддерживает streaming ответов
    - Автоматическое цитирование источников
    - Генерация markdown отчетов
    """
    
    name = "research_agent"
    title = "Агент исследований"
    description = "Глубокое веб-исследование с помощью SGR и Tavily"
    is_public = True
    
    llm_config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.3
    }
    
    prompt = """
Ты агент глубоких исследований с доступом к SGR Deep Research сервису.

ВОЗМОЖНОСТИ:
- sgr_research: Глубокое исследование темы с анализом множества источников
- sgr_quick_search: Быстрый поиск по конкретному вопросу

КОГДА ИСПОЛЬЗОВАТЬ:
- Пользователь просит "исследовать", "найди информацию", "что известно о"
- Нужен детальный анализ темы с несколькими источниками
- Требуется актуальная информация из интернета

КАК РАБОТАТЬ:
1. Для комплексных вопросов используй sgr_research (детальный анализ)
2. Для быстрых фактов используй sgr_quick_search
3. ВСЕГДА передавай полный запрос пользователя в инструмент
4. После получения результата, представь его пользователю

ФОРМАТ ОТВЕТА:
- Структурируй информацию логично
- Упоминай ключевые источники
- Выделяй главные выводы
- Будь объективным и точным

ВАЖНО:
- SGR автоматически ищет в интернете через Tavily
- Результаты содержат актуальную информацию
- Цитирование источников встроено в SGR
"""
    
    tools = []  # Инструменты добавляются через @tool декоратор ниже
    
    @staticmethod
    async def _get_sgr_client() -> SGRClient:
        """Создает клиент SGR с конфигурацией из settings"""
        sgr_config = getattr(settings, 'sgr', None)
        
        if not sgr_config:
            raise ValueError(
                "SGR конфигурация не найдена в settings. "
                "Добавьте секцию 'sgr' в conf.json"
            )
        
        base_url = getattr(sgr_config, 'base_url', 'http://localhost:8010')
        api_key = getattr(sgr_config, 'api_key', None)
        timeout = getattr(sgr_config, 'timeout', 300.0)
        
        return SGRClient(
            base_url=base_url,
            timeout=timeout,
            api_key=api_key
        )


# Регистрируем инструменты для агента
from app.core.tool_decorator import tool


@tool(
    is_public=True,
    title="SGR Исследование",
    cost=0.5,
    billing_name="sgr_research",
    free_for_plans=[]
)
async def sgr_research(query: str, detailed: bool = True) -> str:
    """
    Выполняет глубокое исследование темы через SGR Deep Research.
    
    Использует Schema-Guided Reasoning для:
    - Поиска информации в интернете (Tavily)
    - Анализа множества источников
    - Генерации структурированного отчета
    
    Args:
        query: Тема или вопрос для исследования
        detailed: Использовать детальный режим (больше источников)
        
    Returns:
        Результат исследования с ключевыми находками и источниками
        
    Example:
        >>> await sgr_research("Какие тренды в AI в 2025 году?")
        "Основные тренды AI в 2025:
        1. Multimodal AI...
        2. Edge AI...
        
        Источники:
        - https://example.com/ai-trends..."
    """
    if not query:
        raise ValueError("query не может быть пустым")
    
    logger.info(f"🔍 Запуск SGR исследования: {query[:100]}...")
    
    model = "sgr_agent" if detailed else "sgr_tool_calling_agent"
    
    async with await ResearchAgent._get_sgr_client() as client:
        response = await client.research(query, model=model)
        
        if not response.content:
            raise ValueError("SGR не смог найти информацию по запросу")
        
        logger.info(f"✅ SGR исследование завершено: {len(response.content)} символов")
        return response.content


@tool(
    is_public=True,
    title="SGR Быстрый поиск",
    cost=0.1,
    billing_name="sgr_quick_search"
)
async def sgr_quick_search(question: str) -> str:
    """
    Быстрый поиск ответа на конкретный вопрос через SGR.
    
    Использует более легковесный режим для быстрых фактов.
    
    Args:
        question: Конкретный вопрос
        
    Returns:
        Краткий ответ с ключевыми фактами
        
    Example:
        >>> await sgr_quick_search("Кто основатель OpenAI?")
        "OpenAI была основана в 2015 году Sam Altman и Elon Musk..."
    """
    if not question:
        raise ValueError("question не может быть пустым")
    
    logger.info(f"🔍 SGR быстрый поиск: {question[:100]}...")
    
    async with await ResearchAgent._get_sgr_client() as client:
        response = await client.research(question, model="sgr_tool_calling_agent")
        
        if not response.content:
            raise ValueError("Информация не найдена")
        
        return response.content


# Добавляем инструменты к агенту
ResearchAgent.tools = [sgr_research, sgr_quick_search]


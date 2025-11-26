"""
Инструменты для работы с SGR Deep Research сервисом.
"""

import logging
from apps.agents.services.tool_decorator import tool
from apps.agents.clients.sgr_client import SGRClient
from apps.agents.config import get_agents_settings
settings = get_agents_settings()

logger = logging.getLogger(__name__)


async def _get_sgr_client() -> SGRClient:
    """Создает клиент SGR с конфигурацией из settings"""
    import os
    
    sgr_config = getattr(settings, 'sgr', None)
    
    if not sgr_config:
        raise ValueError(
            "SGR конфигурация не найдена в settings. "
            "Добавьте секцию 'sgr' в conf.json"
        )
    
    # Автоопределение URL в зависимости от окружения
    # В Docker используем имя сервиса, локально - localhost
    if os.path.exists('/.dockerenv'):
        base_url = 'http://sgr:8010'
    else:
        base_url = getattr(sgr_config, 'base_url', 'http://localhost:8010')
    
    api_key = getattr(sgr_config, 'api_key', None)
    timeout = getattr(sgr_config, 'timeout', 300.0)
    
    return SGRClient(
        base_url=base_url,
        timeout=timeout,
        api_key=api_key
    )


@tool(
    is_public=True,
    group="Поиск и исследование",
    title="SGR Исследование",
    cost=0.5,
    billing_name="sgr_research"
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
    """
    if not query:
        raise ValueError("query не может быть пустым")
    
    logger.info(f"🔍 Запуск SGR исследования: {query[:100]}...")
    
    model = "sgr_agent" if detailed else "sgr_tool_calling_agent"
    
    async with await _get_sgr_client() as client:
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
    """
    if not question:
        raise ValueError("question не может быть пустым")
    
    logger.info(f"🔍 SGR быстрый поиск: {question[:100]}...")
    
    async with await _get_sgr_client() as client:
        response = await client.research(question, model="sgr_tool_calling_agent")
        
        if not response.content:
            raise ValueError("Информация не найдена")
        
        return response.content


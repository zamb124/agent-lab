"""
Инструменты для поиска через Tavily API.
Tavily - специализированный поисковый API для LLM с ранжированием и фильтрацией.
"""

import logging
import httpx
from typing import Optional, List, Dict, Any
import json

from app.core.tool_decorator import tool
from app.core.config import settings
from app.core.progress_sender import send_progress

logger = logging.getLogger(__name__)


async def _get_tavily_client() -> httpx.AsyncClient:
    """Создает HTTP клиент для Tavily API"""
    api_key = settings.sgr.tavily_api_key if hasattr(settings, 'sgr') and settings.sgr else None
    
    if not api_key:
        raise ValueError(
            "Tavily API key не найден. "
            "Добавьте sgr.tavily_api_key в conf.json"
        )
    
    return httpx.AsyncClient(
        base_url="https://api.tavily.com",
        headers={"Content-Type": "application/json"},
        timeout=30.0
    )


@tool(
    is_public=True,
    title="Поиск Tavily",
    cost=0.05,
    billing_name="tavily_search"
)
async def tavily_search(
    query: str,
    max_results: int = 5
) -> str:
    """
    Поиск информации через Tavily API.
    
    Tavily оптимизирован для LLM - возвращает только релевантный контент
    с высоким качеством и автоматической фильтрацией шума.
    
    Args:
        query: Поисковый запрос
        max_results: Максимальное количество результатов (1-10)
        
    Returns:
        Структурированные результаты поиска с контентом и источниками
        
    Examples:
        tavily_search("современные подходы к RAG", max_results=5)
        tavily_search("новости ИИ 2024")
    """
    if not query:
        raise ValueError("query не может быть пустым")
    
    if max_results < 1 or max_results > 10:
        max_results = 5
    
    logger.info(f"🔍 Tavily поиск: {query[:100]}... (max_results={max_results})")
    
    await send_progress(f"🔍 Ищу информацию через Tavily: '{query[:60]}...'")
    
    status_prefix = f"🔍 Поиск: '{query[:50]}...'\n\n"
    
    async with await _get_tavily_client() as client:
        try:
            response = await client.post(
                "/search",
                json={
                    "api_key": settings.sgr.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": True,
                    "include_raw_content": False,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            if data.get("answer"):
                results.append(f"📌 Краткий ответ: {data['answer']}\n")
            
            if data.get("results"):
                results.append("📚 Источники:\n")
                for i, result in enumerate(data["results"], 1):
                    title = result.get("title", "Без названия")
                    url = result.get("url", "")
                    content = result.get("content", "")
                    score = result.get("score", 0)
                    
                    results.append(
                        f"{i}. {title}\n"
                        f"   URL: {url}\n"
                        f"   Релевантность: {score:.2f}\n"
                        f"   Контент: {content[:300]}...\n"
                    )
            
            formatted_results = "\n".join(results)
            logger.info(f"✅ Tavily: найдено {len(data.get('results', []))} результатов")
            
            # Добавляем статус для пользователя
            final_result = status_prefix + formatted_results if formatted_results else "Результаты не найдены"
            return final_result
            
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ошибка Tavily API ({e.response.status_code}): {e.response.text[:200]}"
            ) from e


@tool(
    is_public=True,
    title="Tavily расширенный поиск",
    cost=0.1,
    billing_name="tavily_search_advanced"
)
async def tavily_search_advanced(
    query: str,
    search_depth: str = "advanced",
    include_domains: Optional[str] = None,
    exclude_domains: Optional[str] = None
) -> str:
    """
    Расширенный поиск через Tavily с дополнительными опциями.
    
    Args:
        query: Поисковый запрос
        search_depth: Глубина поиска ("basic" или "advanced")
        include_domains: Домены для включения (через запятую)
        exclude_domains: Домены для исключения (через запятую)
        
    Returns:
        Детальные результаты поиска с полным контентом
        
    Examples:
        tavily_search_advanced(
            "LangGraph tutorial",
            search_depth="advanced",
            include_domains="langchain.com,github.com"
        )
    """
    if not query:
        raise ValueError("query не может быть пустым")
    
    logger.info(f"🔍 Tavily расширенный поиск: {query[:100]}...")
    
    request_data: Dict[str, Any] = {
        "api_key": settings.sgr.tavily_api_key,
        "query": query,
        "max_results": 10,
        "search_depth": search_depth,
        "include_answer": True,
        "include_raw_content": True,
    }
    
    if include_domains:
        request_data["include_domains"] = [d.strip() for d in include_domains.split(",")]
    
    if exclude_domains:
        request_data["exclude_domains"] = [d.strip() for d in exclude_domains.split(",")]
    
    async with await _get_tavily_client() as client:
        try:
            response = await client.post("/search", json=request_data)
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            if data.get("answer"):
                results.append(f"📌 Развернутый ответ:\n{data['answer']}\n")
            
            if data.get("results"):
                results.append(f"📚 Найдено {len(data['results'])} детальных источников:\n")
                for i, result in enumerate(data["results"], 1):
                    title = result.get("title", "Без названия")
                    url = result.get("url", "")
                    content = result.get("content", "")
                    raw_content = result.get("raw_content", "")
                    score = result.get("score", 0)
                    
                    results.append(
                        f"{i}. [{title}]({url})\n"
                        f"   Релевантность: {score:.2f}\n"
                        f"   Контент: {content}\n"
                    )
                    
                    if raw_content and len(raw_content) > len(content):
                        results.append(f"   Полный текст: {raw_content[:500]}...\n")
            
            formatted_results = "\n".join(results)
            logger.info(f"✅ Tavily advanced: найдено {len(data.get('results', []))} результатов")
            
            return formatted_results if formatted_results else "Результаты не найдены"
            
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ошибка Tavily API ({e.response.status_code}): {e.response.text[:200]}"
            ) from e


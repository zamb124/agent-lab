"""
Инструменты для поиска через Serper API (Google Search).
Serper предоставляет доступ к Google Search результатам через API.
"""

import logging
import httpx
from typing import Optional

from app.core.tool_decorator import tool

logger = logging.getLogger(__name__)


@tool(
    is_public=True,
    group="Поиск и исследование",
    title="Google поиск (Serper)",
    cost=0.03,
    billing_name="serper_search"
)
async def serper_search(
    query: str,
    num_results: int = 10,
    country: str = "us"
) -> str:
    """
    Поиск через Google с помощью Serper API.
    
    Возвращает органические результаты Google поиска с snippets.
    Полезен для поиска актуальной информации и новостей.
    
    Args:
        query: Поисковый запрос
        num_results: Количество результатов (1-100)
        country: Код страны для локализации (us, ru, uk)
        
    Returns:
        Результаты Google поиска с описаниями
        
    Examples:
        serper_search("LangGraph documentation", num_results=5)
        serper_search("новости ИИ", country="ru")
        
    Note:
        Требует SERPER_API_KEY в переменных окружения
    """
    if not query:
        raise ValueError("query не может быть пустым")
    
    logger.info(f"🔍 Serper Google поиск: {query[:100]}...")
    
    import os
    api_key = os.getenv("SERPER_API_KEY")
    
    if not api_key:
        return (
            "⚠️ SERPER_API_KEY не найден в переменных окружения.\n"
            "Получите ключ на https://serper.dev и добавьте в .env:\n"
            "SERPER_API_KEY=your_key_here"
        )
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "q": query,
                    "num": min(num_results, 100),
                    "gl": country
                }
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            if data.get("answerBox"):
                answer = data["answerBox"]
                if "answer" in answer:
                    results.append(f"📌 Прямой ответ: {answer['answer']}\n")
                elif "snippet" in answer:
                    results.append(f"📌 Прямой ответ: {answer['snippet']}\n")
            
            if data.get("organic"):
                results.append("📚 Результаты поиска:\n")
                for i, result in enumerate(data["organic"], 1):
                    title = result.get("title", "Без названия")
                    link = result.get("link", "")
                    snippet = result.get("snippet", "")
                    
                    results.append(
                        f"{i}. {title}\n"
                        f"   URL: {link}\n"
                        f"   Описание: {snippet}\n"
                    )
            
            formatted_results = "\n".join(results)
            logger.info(f"✅ Serper: найдено {len(data.get('organic', []))} результатов")
            
            return formatted_results if formatted_results else "Результаты не найдены"
            
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ошибка Serper API ({e.response.status_code}): {e.response.text[:200]}"
            ) from e


@tool(
    is_public=True,
    title="Google новости (Serper)",
    cost=0.03,
    billing_name="serper_news"
)
async def serper_news_search(
    query: str,
    num_results: int = 10
) -> str:
    """
    Поиск новостей через Google News с помощью Serper API.
    
    Возвращает актуальные новостные статьи по запросу.
    
    Args:
        query: Поисковый запрос
        num_results: Количество новостей (1-100)
        
    Returns:
        Новостные статьи с датами и источниками
        
    Examples:
        serper_news_search("искусственный интеллект", num_results=5)
        serper_news_search("LangChain updates")
    """
    if not query:
        raise ValueError("query не может быть пустым")
    
    logger.info(f"📰 Serper новости: {query[:100]}...")
    
    import os
    api_key = os.getenv("SERPER_API_KEY")
    
    if not api_key:
        return "⚠️ SERPER_API_KEY не найден в переменных окружения"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "https://google.serper.dev/news",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "q": query,
                    "num": min(num_results, 100)
                }
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            if data.get("news"):
                results.append(f"📰 Найдено {len(data['news'])} новостей:\n")
                for i, article in enumerate(data["news"], 1):
                    title = article.get("title", "Без названия")
                    link = article.get("link", "")
                    snippet = article.get("snippet", "")
                    source = article.get("source", "")
                    date = article.get("date", "")
                    
                    results.append(
                        f"{i}. {title}\n"
                        f"   Источник: {source} | Дата: {date}\n"
                        f"   URL: {link}\n"
                        f"   {snippet}\n"
                    )
            
            formatted_results = "\n".join(results)
            logger.info(f"✅ Serper news: найдено {len(data.get('news', []))} новостей")
            
            return formatted_results if formatted_results else "Новости не найдены"
            
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ошибка Serper API ({e.response.status_code}): {e.response.text[:200]}"
            ) from e


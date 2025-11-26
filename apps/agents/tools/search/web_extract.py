"""
Инструменты для извлечения контента с веб-страниц.
Используются для получения полного текста статей и документов.
"""

import logging
import httpx
from typing import Dict, Any
from bs4 import BeautifulSoup

from apps.agents.services.tool_decorator import tool

logger = logging.getLogger(__name__)


@tool(
    is_public=True,
    group="Поиск и исследование",
    title="Извлечь контент страницы",
    cost=0.01,
    billing_name="extract_web_content"
)
async def extract_web_content(
    url: str,
    max_length: int = 5000
) -> str:
    """
    Извлекает текстовый контент с веб-страницы.
    
    Удаляет HTML разметку, скрипты, стили и оставляет только читаемый текст.
    Полезно для получения полного содержания статей.
    
    Args:
        url: URL страницы для извлечения
        max_length: Максимальная длина текста в символах
        
    Returns:
        Очищенный текстовый контент страницы
        
    Examples:
        extract_web_content("https://example.com/article")
        extract_web_content("https://docs.langchain.com", max_length=3000)
    """
    if not url:
        raise ValueError("url не может быть пустым")
    
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Небезопасный URL: {url}")
    
    logger.info(f"🌐 Извлечение контента: {url}")
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"
        }
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            text = soup.get_text(separator="\n", strip=True)
            
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            clean_text = "\n".join(lines)
            
            if len(clean_text) > max_length:
                clean_text = clean_text[:max_length] + "..."
            
            logger.info(f"✅ Извлечено {len(clean_text)} символов из {url}")
            
            return clean_text if clean_text else "Контент не найден на странице"
            
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ошибка HTTP ({e.response.status_code}) при загрузке {url}: "
                f"{e.response.text[:100]}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Ошибка извлечения контента из {url}: {str(e)}"
            ) from e


@tool(
    is_public=True,
    title="Извлечь метаданные страницы",
    cost=0.005,
    billing_name="extract_metadata"
)
async def extract_metadata(url: str) -> str:
    """
    Извлекает метаданные страницы (title, description, keywords).
    
    Полезно для быстрой оценки релевантности страницы без загрузки всего контента.
    
    Args:
        url: URL страницы
        
    Returns:
        Структурированные метаданные страницы
        
    Examples:
        extract_metadata("https://example.com/article")
    """
    if not url:
        raise ValueError("url не может быть пустым")
    
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Небезопасный URL: {url}")
    
    logger.info(f"📋 Извлечение метаданных: {url}")
    
    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"
        }
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            metadata: Dict[str, Any] = {}
            
            title_tag = soup.find("title")
            if title_tag:
                metadata["title"] = title_tag.get_text().strip()
            
            og_title = soup.find("meta", property="og:title")
            if og_title and "title" not in metadata:
                metadata["title"] = og_title.get("content", "").strip()
            
            description = soup.find("meta", attrs={"name": "description"})
            if description:
                metadata["description"] = description.get("content", "").strip()
            
            og_description = soup.find("meta", property="og:description")
            if og_description and "description" not in metadata:
                metadata["description"] = og_description.get("content", "").strip()
            
            keywords = soup.find("meta", attrs={"name": "keywords"})
            if keywords:
                metadata["keywords"] = keywords.get("content", "").strip()
            
            author = soup.find("meta", attrs={"name": "author"})
            if author:
                metadata["author"] = author.get("content", "").strip()
            
            result = [f"📄 Метаданные для {url}:\n"]
            for key, value in metadata.items():
                result.append(f"{key.capitalize()}: {value}")
            
            formatted = "\n".join(result)
            logger.info(f"✅ Извлечены метаданные из {url}")
            
            return formatted if metadata else "Метаданные не найдены"
            
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ошибка HTTP ({e.response.status_code}) при загрузке {url}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Ошибка извлечения метаданных из {url}: {str(e)}"
            ) from e


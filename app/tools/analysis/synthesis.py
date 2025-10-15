"""
Инструменты для синтеза информации и создания отчетов.
"""

import logging
import json
from typing import Optional

from app.core.tool_decorator import tool
from app.core.llm_factory import get_llm
from app.core.progress_sender import send_progress

logger = logging.getLogger(__name__)


@tool(
    is_public=True,
    title="Синтезировать отчет",
    cost=0.05,
    billing_name="synthesize_report"
)
async def synthesize_report(
    query: str,
    facts_json: str,
    sources: str = ""
) -> str:
    """
    Создает итоговый исследовательский отчет на основе фактов.
    
    Args:
        query: Исходный запрос пользователя
        facts_json: JSON список извлеченных фактов
        sources: Список источников (опционально)
        
    Returns:
        Полный структурированный отчет в markdown
        
    Examples:
        synthesize_report(
            "Что такое RAG?",
            '[{"statement": "...", ...}]',
            sources="1. example.com\n2. another.com"
        )
    """
    if not query:
        raise ValueError("query не может быть пустым")
    if not facts_json:
        raise ValueError("facts_json не может быть пустым")
    
    logger.info(f"📝 Синтез отчета для запроса: {query[:100]}...")
    
    await send_progress(f"📝 Синтезирую итоговый отчет...")
    
    status_message = f"📝 Синтез отчета\n\n"
    
    try:
        facts = json.loads(facts_json)
    except json.JSONDecodeError:
        facts = []
        logger.warning("Не удалось распарсить факты, используем текст как есть")
    
    llm = get_llm()
    
    prompt = f"""Создай детальный исследовательский отчет по запросу: "{query}"

На основе следующих извлеченных фактов:
{json.dumps(facts, ensure_ascii=False, indent=2) if facts else facts_json}

Структура отчета:
# [Название отчета]

## 📋 Краткое резюме
[2-3 предложения с ключевыми выводами]

## 🔍 Детальный анализ
[Разделы по категориям фактов с подробным описанием]

## ✨ Ключевые выводы
[Список основных выводов]

## 📚 Источники
{sources if sources else "[Источники будут добавлены]"}

Требования:
- Используй markdown форматирование
- Цитируй факты там где уместно
- Будь объективным и структурированным
- Используй эмодзи для разделов (как в примере)
- Если есть противоречия - отметь их"""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Отчет синтезирован ({len(result)} символов)")
    return status_message + f"Отчет готов ({len(result)} символов)\n\n{result}"


@tool(
    is_public=True,
    title="Форматировать в markdown",
    cost=0.01,
    billing_name="format_markdown"
)
async def format_markdown(
    text: str,
    style: str = "academic"
) -> str:
    """
    Форматирует текст в красивый markdown с правильной структурой.
    
    Args:
        text: Текст для форматирования
        style: Стиль форматирования ("academic", "business", "casual")
        
    Returns:
        Отформатированный markdown текст
        
    Examples:
        format_markdown("Неструктурированный текст...", style="academic")
    """
    if not text:
        raise ValueError("text не может быть пустым")
    
    logger.info(f"💅 Форматирование в markdown (стиль: {style})")
    
    llm = get_llm()
    
    style_instructions = {
        "academic": "Академический стиль: строгая структура, заголовки, списки, цитаты",
        "business": "Деловой стиль: краткость, bullet points, выделение ключевых метрик",
        "casual": "Неформальный стиль: простой язык, эмодзи, дружелюбный тон"
    }
    
    instruction = style_instructions.get(style, style_instructions["academic"])
    
    prompt = f"""Отформатируй следующий текст в markdown.

Стиль: {instruction}

Текст:
{text}

Требования:
- Создай логическую структуру с заголовками
- Используй списки где уместно
- Выдели важные моменты (bold, italic)
- Добавь разделители где нужно
- Сохрани всю информацию из исходного текста"""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Форматирование завершено")
    return result


@tool(
    is_public=True,
    title="Создать цитирование",
    cost=0.01,
    billing_name="create_citations"
)
async def create_citations(
    sources: str,
    format: str = "apa"
) -> str:
    """
    Создает правильно отформатированные цитаты источников.
    
    Args:
        sources: Список источников (URLs или описания)
        format: Формат цитирования ("apa", "mla", "chicago", "simple")
        
    Returns:
        Отформатированный список цитат
        
    Examples:
        create_citations("https://example.com\nhttps://another.com", format="apa")
    """
    if not sources:
        raise ValueError("sources не может быть пустым")
    
    logger.info(f"📚 Создание цитирования в формате: {format}")
    
    llm = get_llm()
    
    format_instructions = {
        "apa": "APA 7th edition формат",
        "mla": "MLA 9th edition формат",
        "chicago": "Chicago style формат",
        "simple": "Простой формат: название, URL, дата доступа"
    }
    
    instruction = format_instructions.get(format, format_instructions["simple"])
    
    prompt = f"""Создай правильно отформатированные цитаты для следующих источников.

Формат: {instruction}

Источники:
{sources}

Для каждого источника:
- Если это URL - получи название из контекста или используй домен
- Добавь дату доступа (используй текущую дату)
- Пронумеруй источники

Верни список в markdown формате."""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Цитирование создано")
    return result


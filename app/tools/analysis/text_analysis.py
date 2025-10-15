"""
Инструменты для анализа текста.
Используют LLM для глубокого понимания и обработки текстовых данных.
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
    title="Анализ текста",
    cost=0.02,
    billing_name="analyze_text"
)
async def analyze_text(
    text: str,
    focus: str = "general"
) -> str:
    """
    Глубокий анализ текста с извлечением структуры и ключевых моментов.
    
    Args:
        text: Текст для анализа
        focus: Фокус анализа ("general", "technical", "business", "academic")
        
    Returns:
        Структурированный анализ текста
        
    Examples:
        analyze_text("Длинная статья о RAG...", focus="technical")
    """
    if not text:
        raise ValueError("text не может быть пустым")
    
    logger.info(f"📊 Анализ текста ({len(text)} символов), фокус: {focus}")
    
    await send_progress(f"📊 Анализирую текст ({len(text)} символов)...")
    
    llm = get_llm()
    
    status_message = f"📊 Анализ текста (фокус: {focus})\n\n"
    
    prompt = f"""Проанализируй следующий текст с фокусом на {focus}.

Предоставь:
1. Основная тема (1-2 предложения)
2. Ключевые концепции (список 3-5 пунктов)
3. Тип контента (статья, документация, новость, и т.д.)
4. Уровень сложности (начальный, средний, продвинутый)
5. Целевая аудитория

Текст:
{text[:3000]}

Формат ответа - структурированный текст."""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Анализ текста завершен")
    return status_message + result


@tool(
    is_public=True,
    title="Извлечь ключевые моменты",
    cost=0.015,
    billing_name="extract_key_points"
)
async def extract_key_points(
    text: str,
    max_points: int = 5
) -> str:
    """
    Извлекает ключевые моменты из текста.
    
    Args:
        text: Текст для обработки
        max_points: Максимальное количество ключевых моментов
        
    Returns:
        Список ключевых моментов
        
    Examples:
        extract_key_points("Статья о новых возможностях LangGraph...", max_points=3)
    """
    if not text:
        raise ValueError("text не может быть пустым")
    
    logger.info(f"🔑 Извлечение {max_points} ключевых моментов")
    
    llm = get_llm()
    
    prompt = f"""Извлеки {max_points} самых важных ключевых моментов из текста.

Текст:
{text[:3000]}

Формат ответа:
1. [Первый ключевой момент]
2. [Второй ключевой момент]
...

Каждый момент должен быть конкретным и информативным (1-2 предложения)."""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Извлечено {max_points} ключевых моментов")
    return result


@tool(
    is_public=True,
    title="Суммаризировать текст",
    cost=0.02,
    billing_name="summarize_text"
)
async def summarize_text(
    text: str,
    length: str = "medium"
) -> str:
    """
    Создает краткое резюме текста.
    
    Args:
        text: Текст для суммаризации
        length: Длина резюме ("short" - 2-3 предложения, "medium" - параграф, "long" - несколько параграфов)
        
    Returns:
        Краткое резюме текста
        
    Examples:
        summarize_text("Длинный текст...", length="short")
    """
    if not text:
        raise ValueError("text не может быть пустым")
    
    logger.info(f"📝 Суммаризация текста ({len(text)} символов), длина: {length}")
    
    length_instructions = {
        "short": "2-3 предложения",
        "medium": "1 параграф (5-7 предложений)",
        "long": "2-3 параграфа"
    }
    
    target_length = length_instructions.get(length, length_instructions["medium"])
    
    llm = get_llm()
    
    prompt = f"""Создай краткое резюме следующего текста.

Длина резюме: {target_length}

Требования:
- Сохрани ключевые факты и идеи
- Используй простой и понятный язык
- Будь объективным

Текст:
{text[:4000]}

Резюме:"""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Суммаризация завершена")
    return result


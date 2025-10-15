"""
Инструменты для извлечения и верификации фактов из текста.
"""

import logging
import json
from typing import List, Dict, Any

from app.core.tool_decorator import tool
from app.core.llm_factory import get_llm
from app.core.progress_sender import send_progress

logger = logging.getLogger(__name__)


@tool(
    is_public=True,
    title="Извлечь факты",
    cost=0.03,
    billing_name="extract_facts"
)
async def extract_facts(
    text: str,
    source_url: str = ""
) -> str:
    """
    Извлекает конкретные факты из текста с оценкой достоверности.
    
    Args:
        text: Текст для извлечения фактов
        source_url: URL источника (опционально)
        
    Returns:
        JSON список фактов с метаданными
        
    Examples:
        extract_facts("Статья о RAG...", source_url="https://example.com")
    """
    if not text:
        raise ValueError("text не может быть пустым")
    
    logger.info(f"🔬 Извлечение фактов из текста ({len(text)} символов)")
    
    await send_progress(f"🔬 Извлекаю факты из текста...")
    
    llm = get_llm()
    
    status_message = f"🔬 Извлечение фактов\n\n"
    
    prompt = f"""Извлеки конкретные, проверяемые факты из следующего текста.

Для каждого факта определи:
1. statement - само утверждение (конкретное и четкое)
2. confidence - уверенность в достоверности (0.0-1.0)
3. category - категория факта (определение, статистика, событие, мнение)
4. context - краткий контекст (опционально)

Текст:
{text[:3000]}

Источник: {source_url if source_url else "не указан"}

Верни результат В ВИДЕ ВАЛИДНОГО JSON:
[
  {{
    "statement": "...",
    "confidence": 0.9,
    "category": "статистика",
    "context": "..."
  }},
  ...
]

Извлекай только факты, НЕ мнения (если это не явно указано как мнение)."""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    try:
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()
        
        facts = json.loads(result)
        
        if source_url:
            for fact in facts:
                fact["source"] = source_url
        
        logger.info(f"✅ Извлечено {len(facts)} фактов")
        return status_message + f"Извлечено {len(facts)} фактов\n\n" + json.dumps(facts, ensure_ascii=False, indent=2)
        
    except json.JSONDecodeError as e:
        logger.warning(f"Не удалось распарсить JSON: {e}")
        return status_message + result


@tool(
    is_public=True,
    title="Верифицировать факты",
    cost=0.025,
    billing_name="verify_facts"
)
async def verify_facts(
    facts_json: str
) -> str:
    """
    Проверяет факты на непротиворечивость и логичность.
    
    Args:
        facts_json: JSON список фактов для проверки
        
    Returns:
        Отчет о верификации с потенциальными проблемами
        
    Examples:
        verify_facts('[{"statement": "...", "confidence": 0.9}]')
    """
    if not facts_json:
        raise ValueError("facts_json не может быть пустым")
    
    logger.info(f"✅ Верификация фактов")
    
    try:
        facts = json.loads(facts_json)
    except json.JSONDecodeError:
        return "Ошибка: факты должны быть в JSON формате"
    
    llm = get_llm()
    
    prompt = f"""Проверь следующие факты на:
1. Непротиворечивость между собой
2. Логическую согласованность
3. Потенциальные ошибки или неточности

Факты:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Верни отчет о верификации:
- Найденные противоречия (если есть)
- Факты с низкой достоверностью (confidence < 0.6)
- Рекомендации по улучшению

Если все хорошо - напиши "Все факты согласованы"."""

    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Верификация завершена")
    return result


@tool(
    is_public=True,
    title="Структурировать факты",
    cost=0.02,
    billing_name="structure_facts"
)
async def structure_facts(
    facts_json: str,
    structure_type: str = "category"
) -> str:
    """
    Структурирует факты по категориям или темам.
    
    Args:
        facts_json: JSON список фактов
        structure_type: Тип структурирования ("category", "chronology", "importance")
        
    Returns:
        Структурированное представление фактов
        
    Examples:
        structure_facts('[{...}]', structure_type="category")
    """
    if not facts_json:
        raise ValueError("facts_json не может быть пустым")
    
    logger.info(f"📊 Структурирование фактов по: {structure_type}")
    
    try:
        facts = json.loads(facts_json)
    except json.JSONDecodeError:
        return "Ошибка: факты должны быть в JSON формате"
    
    llm = get_llm(model="x-ai/grok-code-fast-1", temperature=0.2)
    
    structure_instructions = {
        "category": "Сгруппируй факты по логическим категориям (определения, статистика, события, процессы)",
        "chronology": "Упорядочь факты по хронологии (если применимо) или по логической последовательности",
        "importance": "Ранжируй факты по важности и влиянию на основной вопрос"
    }
    
    instruction = structure_instructions.get(structure_type, structure_instructions["category"])
    
    llm = get_llm()
    
    prompt = f"""{instruction}

Факты:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Верни структурированное представление в markdown формате с разделами и подразделами."""
    
    response = await llm.ainvoke(prompt)
    result = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"✅ Структурирование завершено")
    return result


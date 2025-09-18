"""
Стандартные инструменты для всех агентов.
"""

import logging
from langchain_core.tools import tool
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt


@tool
def ask_user(question: str) -> str:
    """
    Запросить информацию у пользователя.

    Args:
        question: Вопрос для пользователя

    Returns:
        Ответ пользователя в формате "QUESTION: вопрос\nANSWER: ответ"
    """
    logger = logging.getLogger(__name__)

    logger.info(f"🔵 ask_user tool вызван с вопросом: {question}")
    logger.info(f"🔵 Вызываем interrupt() с вопросом: {question}")

    try:
        result = interrupt(question)
        logger.info(f"🟢 ask_user получил ответ: {result}")

        # КРИТИЧНО: Возвращаем в формате, который понимает агент
        formatted_result = f"QUESTION: {question}\nANSWER: {result}"
        logger.info(f"📝 Форматированный результат: {formatted_result}")
        return formatted_result

    except GraphInterrupt as e:
        logger.error(f"🔴 Ошибка в ask_user tool: {e}")
        raise

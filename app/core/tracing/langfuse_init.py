"""
Инициализация Langfuse для observability LLM-вызовов.

Используется только для callback-трейсинга агентов.
Автоматически включается если включен OTEL и есть переменные окружения.
"""

import logging
import os
from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_callback_handler = None

"""Используется только для расширения трейса, выгрузку в langfuse не делаем"""
def get_langfuse_callback():
    """
    Возвращает Langfuse callback handler для трейсинга агентов.

    Автоматически включается если:
    - Включен OTEL трейсинг (settings.otel.enabled)
    - Заданы переменные окружения LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY

    Returns:
        CallbackHandler если Langfuse доступен, иначе None
    """
    global _langfuse_callback_handler

    if not settings.otel.enabled:
        return None

    if _langfuse_callback_handler is not None:
        return _langfuse_callback_handler


    from langfuse.langchain import CallbackHandler
    _langfuse_callback_handler = CallbackHandler(update_trace=True)

    return _langfuse_callback_handler


"""
Фабрика для создания callback handlers.

Предоставляет унифицированный способ получения callback handler'ов
для LangChain/LangGraph с учетом текущих настроек трейсинга.
"""

import logging
from typing import Optional, List

from core.config import get_settings
from apps.agents.services.tracing.callback_handler import OpenTelemetryCallbackHandler

logger = logging.getLogger(__name__)


def get_otel_callback_handler(
    tracer_name: str = "langchain",
) -> Optional[OpenTelemetryCallbackHandler]:
    """
    Создать OpenTelemetry callback handler для LangChain/LangGraph.

    Автоматически проверяет, включен ли OTEL трейсинг в конфигурации.

    Args:
        tracer_name: Имя tracer'а (по умолчанию "langchain")

    Returns:
        OpenTelemetryCallbackHandler если трейсинг включен, иначе None

    Example:
        ```python
        from apps.agents.services.tracing.callback_factory import get_otel_callback_handler

        # В агенте/графе
        callback = get_otel_callback_handler()
        if callback:
            result = await agent.ainvoke(
                {"messages": messages},
                config={"callbacks": [callback]}
            )
        ```
    """
    settings = get_settings()

    if not settings.otel.enabled:
        logger.debug("OTEL трейсинг отключен, callback handler не создан")
        return None

    try:
        handler = OpenTelemetryCallbackHandler(tracer_name=tracer_name)
        logger.debug(f"✅ Создан OpenTelemetry callback handler (tracer={tracer_name})")
        return handler
    except Exception as e:
        logger.error(f"Ошибка создания callback handler: {e}", exc_info=True)
        return None


def get_callbacks_for_agent() -> List:
    """
    Получить список callback handlers для агента.

    Автоматически добавляет все активные callback handlers
    (OTEL, Langfuse, etc.) в зависимости от конфигурации.

    Returns:
        Список активных callback handlers

    Example:
        ```python
        from apps.agents.services.tracing.callback_factory import get_callbacks_for_agent

        # В агенте
        callbacks = get_callbacks_for_agent()
        result = await agent.ainvoke(
            {"messages": messages},
            config={"callbacks": callbacks}
        )
        ```
    """
    callbacks = []

    # OTEL callback
    otel_callback = get_otel_callback_handler()
    if otel_callback:
        callbacks.append(otel_callback)

    # Здесь можно добавить другие callback handlers
    # например, для логирования, мониторинга, etc.

    return callbacks



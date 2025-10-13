"""
Фабрика для создания LLM через OpenRouter.
"""

import logging
from typing import Optional
from langchain_core.language_models import BaseLLM

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def get_llm(model: Optional[str] = None, **kwargs) -> BaseLLM:
    """
    Создает LLM через OpenRouter.

    Args:
        model: ID модели в формате "provider/model" (например, "anthropic/claude-sonnet-4.5")
        **kwargs: Дополнительные параметры (temperature, max_tokens, etc.)

    Returns:
        Экземпляр LLM с биллингом
    """
    settings = get_settings()
    openrouter_config = settings.llm.openrouter

    if not openrouter_config.enabled:
        raise ValueError("OpenRouter отключен в конфигурации")

    model_name = model or settings.llm.default_model

    # Получаем конфигурацию модели
    model_config = settings.llm.models.get(model_name)
    
    # Собираем параметры для LLM
    llm_kwargs = {
        "base_url": openrouter_config.base_url,
        "api_key": openrouter_config.api_key,
        "model": model_name,
        "timeout": openrouter_config.timeout,
        "max_retries": openrouter_config.max_retries,
    }

    # Добавляем настройки из конфигурации модели
    if model_config:
        if model_config.temperature is not None:
            llm_kwargs["temperature"] = model_config.temperature
        if model_config.max_tokens is not None:
            llm_kwargs["max_tokens"] = model_config.max_tokens
    
    # Добавляем OpenRouter-специфичные headers для статистики
    llm_kwargs["default_headers"] = {
        "HTTP-Referer": openrouter_config.site_url,
        "X-Title": openrouter_config.site_name,
    }

        # Переопределяем параметрами от агента
    for key, value in kwargs.items():
        if key not in ["api_key", "base_url"]:  # Эти параметры всегда из конфига
            llm_kwargs[key] = value

    logger.info(f"Создаем LLM через OpenRouter: {model_name}")

    from app.core.llm_billing_wrapper import ChatOpenAIWithBilling
    return ChatOpenAIWithBilling(**llm_kwargs)

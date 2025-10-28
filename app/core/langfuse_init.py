"""
Инициализация Langfuse для мониторинга LLM вызовов.
Обеспечивает интеграцию с LangChain через callbacks.
"""

import logging
from typing import Optional, Dict, Any
from langfuse import Langfuse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Глобальный экземпляр Langfuse
_langfuse_instance: Optional[Langfuse] = None


def get_langfuse() -> Optional[Langfuse]:
    """
    Получает глобальный экземпляр Langfuse.

    Returns:
        Экземпляр Langfuse или None если отключен
    """
    global _langfuse_instance

    settings = get_settings()
    langfuse_config = settings.langfuse

    if not langfuse_config.enabled:
        logger.debug("Langfuse отключен в конфигурации")
        return None

    if _langfuse_instance is not None:
        return _langfuse_instance


    # Создаем конфигурацию для Langfuse
    config = {
        "public_key": langfuse_config.public_key,
        "secret_key": langfuse_config.secret_key,
        "host": langfuse_config.host,
        "sample_rate": langfuse_config.sample_rate,
        "flush_interval": langfuse_config.flush_interval,
        "flush_at": langfuse_config.flush_at,
    }

    # Удаляем None значения
    config = {k: v for k, v in config.items() if v is not None}

    logger.info(f"Инициализация Langfuse с host: {langfuse_config.host}")

    _langfuse_instance = Langfuse(**config)

    logger.info("Langfuse успешно инициализирован")
    return _langfuse_instance


def get_langfuse_callback() -> Optional[Any]:
    """
    Получает Langfuse callback для интеграции с LangChain.

    Returns:
        Langfuse callback или None если Langfuse отключен
    """
    langfuse = get_langfuse()
    if langfuse is None:
        return None


    from langfuse.langchain import CallbackHandler
    callback = CallbackHandler()
    logger.debug("Langfuse callback создан")
    return callback



def flush_langfuse():
    """
    Принудительно отправляет все накопленные данные в Langfuse.
    Вызывается при завершении работы приложения.
    """
    global _langfuse_instance

    if _langfuse_instance is not None:
        try:
            logger.info("Отправка данных в Langfuse...")
            _langfuse_instance.flush()
            logger.info("Данные успешно отправлены в Langfuse")
        except Exception as e:
            logger.error(f"Ошибка отправки данных в Langfuse: {e}")


def get_langfuse_cost() -> Optional[float]:
    """
    Получает стоимость текущей операции из Langfuse.
    Возвращает стоимость в USD или None если не удалось получить.

    Используется для интеграции с биллинговой системой.
    """
    try:
        langfuse = get_langfuse()
        if not langfuse:
            return None

        # Получаем текущую trace/generation
        # Langfuse хранит стоимость в observation объектах
        current_observation = getattr(langfuse, '_current_observation', None)
        if not current_observation:
            return None

        # Получаем стоимость из observation
        cost_details = getattr(current_observation, 'cost_details', None)
        if cost_details and isinstance(cost_details, dict):
            # Суммируем все стоимости
            total_cost = 0.0
            for cost_type, cost_value in cost_details.items():
                if isinstance(cost_value, (int, float)):
                    total_cost += cost_value

            if total_cost > 0:
                logger.debug(f"Получена стоимость из Langfuse: ${total_cost:.6f}")
                return total_cost

        return None

    except Exception as e:
        logger.error(f"Ошибка получения стоимости из Langfuse: {e}")
        return None


def shutdown_langfuse():
    """
    Корректно завершает работу с Langfuse.
    Вызывается при завершении работы приложения.
    """
    global _langfuse_instance

    if _langfuse_instance is not None:
        try:
            logger.info("Завершение работы Langfuse...")
            flush_langfuse()
            _langfuse_instance = None
            logger.info("Langfuse успешно завершен")
        except Exception as e:
            logger.error(f"Ошибка завершения Langfuse: {e}")

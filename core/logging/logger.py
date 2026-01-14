"""
Настройка логирования приложения.

Система логирования поддерживает несколько форматов:
- JSON формат для файлов
- Structured формат для консоли (красивый вывод с цветами)
- Pretty формат для консоли (текстовый)
"""

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Optional

from core.config import get_settings, LoggingConfig
from core.logging.formatters import JSONFormatter, StructuredConsoleFormatter


def setup_logging(service_name: str = "core", logging_config: Optional[LoggingConfig] = None):
    """
    Настраивает логирование для сервиса.
    
    Args:
        service_name: Имя сервиса (core, agents, frontend, worker)
        logging_config: Конфигурация логирования (если не указана, берется из settings)
    """
    if logging_config is None:
        settings = get_settings()
        logging_config = settings.logging

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, logging_config.level.upper()))
    root_logger.handlers.clear()

    if logging_config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, logging_config.level.upper()))

        if logging_config.console_format == "structured":
            console_formatter = StructuredConsoleFormatter(use_colors=logging_config.console_colors)
        elif logging_config.console_format == "json":
            console_formatter = JSONFormatter()
        else:
            console_formatter = logging.Formatter(logging_config.format)

        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    if logging_config.file_enabled:
        # Выбираем путь к файлу логов в зависимости от сервиса
        # Используем logs/{service_name}.log для разделения логов
        if service_name == "core":
             log_file = Path(logging_config.file_path)
        elif service_name == "worker":
             log_file = Path(logging_config.worker_file_path)
        else:
             # Для crm, agents, frontend и других - свой файл
             log_file = Path(f"logs/{service_name}.log")
        
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=logging_config.file_max_bytes,
            backupCount=logging_config.file_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, logging_config.level.upper()))

        if logging_config.json_format:
            file_formatter = JSONFormatter()
        else:
            file_formatter = logging.Formatter(logging_config.format)

        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    for logger_name, level in logging_config.loggers_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level.upper()))

    # Перехватываем логгеры uvicorn и taskiq, чтобы они использовали наш формат
    # 1. Сначала известные корневые логгеры
    loggers_to_intercept = ["uvicorn", "uvicorn.access", "uvicorn.error", "taskiq"]
    for name in loggers_to_intercept:
        _logger = logging.getLogger(name)
        _logger.handlers = []
        _logger.propagate = True

    # 2. Агрессивный перехват всех уже созданных логгеров (Sub-loggers)
    # TaskIQ создает taskiq.receiver.receiver и другие, которые могут иметь свои handler-ы
    logger_manager = logging.Logger.manager
    existing_loggers = list(logger_manager.loggerDict.keys())

    for name in existing_loggers:
        if name.startswith("taskiq") or name.startswith("uvicorn"):
            _logger = logging.getLogger(name)
            _logger.handlers = []  # Удаляем все хендлеры
            _logger.propagate = True  # Разрешаем всплытие к root

    logging.info(f"Логирование настроено для сервиса: {service_name}")


class Logger:
    """
    Обёртка над стандартным logger с дополнительными методами для LLM логирования.
    """

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, exc_info: bool = False, **kwargs) -> None:
        self._logger.error(msg, *args, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, *args, exc_info: bool = False, **kwargs) -> None:
        self._logger.critical(msg, *args, exc_info=exc_info, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        """Логирует ошибку с traceback"""
        self._logger.exception(msg, *args, **kwargs)

    def log_llm_response(self, response: Any) -> None:
        """Логирует ответ от LLM"""
        response_str = json.dumps(response, ensure_ascii=False, indent=2)
        self._logger.debug(f"LLM RESPONSE:\n{response_str}")


def get_logger(name: str) -> Logger:
    """
    Получает logger с указанным именем.
    
    Args:
        name: Имя logger (обычно __name__)
        
    Returns:
        Настроенный logger с поддержкой LLM методов
    """
    return Logger(name)


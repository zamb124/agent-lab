"""
Настройка логирования приложения.

Система логирования поддерживает несколько форматов:
- JSON формат для файлов
- Structured формат для консоли (красивый вывод с цветами)
- Pretty формат для консоли (текстовый)
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

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
        if service_name == "worker":
            log_file = Path(logging_config.worker_file_path)
        else:
            log_file = Path(logging_config.file_path)
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

    logging.info(f"Логирование настроено для сервиса: {service_name}")


def get_logger(name: str) -> logging.Logger:
    """
    Получает logger с указанным именем.
    
    Args:
        name: Имя logger (обычно __name__)
        
    Returns:
        Настроенный logger
    """
    return logging.getLogger(name)


"""
Настройка логирования приложения.

Система логирования поддерживает два формата:
1. JSON формат (рекомендуется для production) - структурированные логи с контекстом
2. Pretty формат - красивый вывод для разработки

JSON формат включает:
- timestamp: ISO формат времени
- level: уровень логирования
- logger: имя логгера
- message: сообщение
- module, function, line: информация о коде
- process, thread: системная информация
- context: информация из контекста (пользователь, сессия, агент, flow и т.д.)
- exception: информация об исключениях

Пример JSON лога:
{
  "timestamp": "2025-10-22T19:55:42.417000",
  "level": "INFO",
  "logger": "app.main",
  "message": "Приложение запущено",
  "module": "main",
  "function": "startup",
  "line": 123,
  "process": 12345,
  "thread": 123,
  "context": {
    "user": {
      "user_id": "user_123",
      "name": "Иван Иванов",
      "status": "active"
    },
    "company": {
      "company_id": "comp_456",
      "name": "Моя Компания",
      "subdomain": "company"
    },
    "session_id": "session_789",
    "platform": "telegram",
    "agent": {
      "agent_id": "agent_101",
      "name": "FAQ Агент",
      "model": "claude-3"
    },
    "flow": {
      "flow_id": "flow_202",
      "name": "Обработка жалоб",
      "entry_point_agent": "complaint_agent"
    }
  }
}
"""

import logging
import logging.handlers
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.config import get_settings


class JSONFormatter(logging.Formatter):
    """JSON форматтер для структурированных логов"""

    def format(self, record):
        # Базовые поля лог-записи
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        # Добавляем информацию из контекста
        try:
            from app.core.context import get_context
            context = get_context()

            if context:
                context_info = {}

                # Информация о пользователе
                if context.user:
                    try:
                        context_info["user"] = {
                            "user_id": getattr(context.user, 'user_id', 'unknown'),
                            "name": getattr(context.user, 'name', 'unknown'),
                            "status": getattr(context.user.status, 'value', str(context.user.status)) if hasattr(context.user, 'status') else 'unknown'
                        }
                    except Exception:
                        context_info["user"] = {"error": "failed to extract user info"}

                # Информация о компании
                if context.active_company:
                    try:
                        context_info["company"] = {
                            "company_id": getattr(context.active_company, 'company_id', 'unknown'),
                            "name": getattr(context.active_company, 'name', 'unknown'),
                            "subdomain": getattr(context.active_company, 'subdomain', 'unknown')
                        }
                    except Exception:
                        context_info["company"] = {"error": "failed to extract company info"}

                # Сессия
                if context.session_id:
                    context_info["session_id"] = context.session_id

                # Платформа
                context_info["platform"] = context.platform

                # Агент
                if context.agent_config:
                    try:
                        context_info["agent"] = {
                            "agent_id": getattr(context.agent_config, 'agent_id', 'unknown'),
                            "name": getattr(context.agent_config, 'name', 'unknown'),
                            "model": getattr(context.agent_config, 'model', 'unknown')
                        }
                    except Exception:
                        context_info["agent"] = {"error": "failed to extract agent info"}

                # Flow
                if context.flow_config:
                    try:
                        context_info["flow"] = {
                            "flow_id": getattr(context.flow_config, 'flow_id', 'unknown'),
                            "name": getattr(context.flow_config, 'name', 'unknown'),
                            "entry_point_agent": str(getattr(context.flow_config, 'entry_point_agent', 'unknown'))
                        }
                    except Exception:
                        context_info["flow"] = {"error": "failed to extract flow info"}

                # Переменные flow (если не пустые)
                if context.flow_variables:
                    context_info["flow_variables"] = context.flow_variables

                # State (если есть и не слишком большой)
                if context.state and len(str(context.state)) < 1000:  # Ограничение размера
                    context_info["state"] = context.state

                # Метаданные (если есть)
                if context.metadata:
                    context_info["metadata"] = context.metadata

                if context_info:
                    log_entry["context"] = context_info

        except Exception as e:
            # Если не удалось получить контекст, добавляем информацию об ошибке
            log_entry["context_error"] = str(e)

        # Добавляем exc_info если есть
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Добавляем дополнительные поля из record
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class PrettyJSONFormatter(logging.Formatter):
    """Форматтер для красивого вывода JSON в логах (для обратной совместимости)"""

    def format(self, record):
        msg = super().format(record)
        # Ищем JSON в сообщении и форматируем его
        if "json_data" in msg or "Request options" in msg or "Response" in msg:
            try:
                # Пытаемся найти и отформатировать JSON
                import re
                json_match = re.search(r"\{.*\}", msg, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        json_obj = eval(json_str)  # Осторожно! Только для логов
                        pretty_json = json.dumps(json_obj, indent=2, ensure_ascii=False)
                        msg = msg.replace(json_str, f"\n{pretty_json}")
                    except Exception:
                        pass
            except Exception:
                pass
        return msg


def setup_logging(component: str = "app") -> None:
    """
    Настраивает логирование для указанного компонента.

    Args:
        component: Компонент приложения ("app" или "worker")
    """
    settings = get_settings()
    logging_config = settings.logging

    # Получаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, logging_config.level.upper()))

    # Очищаем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Создаем форматтер на основе настроек
    if logging_config.json_format:
        formatter = JSONFormatter()
    else:
        formatter = PrettyJSONFormatter(logging_config.format)

    # Настраиваем файл для логирования
    if logging_config.file_enabled:
        # Создаем директорию для логов
        log_dir = Path(logging_config.file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Выбираем файл в зависимости от компонента
        if component == "worker":
            log_file = logging_config.worker_file_path
        else:
            log_file = logging_config.app_file_path

        # Создаем директорию для файла компонента
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Создаем RotatingFileHandler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=logging_config.file_max_bytes,
            backupCount=logging_config.file_backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Настраиваем консольный вывод
    if logging_config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Применяем индивидуальные уровни логирования для конкретных логгеров
    for logger_name, level_str in logging_config.loggers_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level_str.upper()))

    # Специальная настройка для OpenAI логов
    for logger_name in ["openai._base_client", "openai", "httpx", "httpcore"]:
        logger_obj = logging.getLogger(logger_name)
        # Применяем соответствующий форматтер ко всем обработчикам OpenAI логгеров
        for handler in logger_obj.handlers:
            if logging_config.json_format:
                handler.setFormatter(JSONFormatter())
            else:
                handler.setFormatter(PrettyJSONFormatter(logging_config.format))


def get_logger(name: str) -> logging.Logger:
    """
    Получает логгер с указанным именем.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def setup_app_logging() -> None:
    """Настраивает логирование для основного приложения"""
    setup_logging("app")


def setup_worker_logging() -> None:
    """Настраивает логирование для воркера"""
    setup_logging("worker")


def log_extra(logger: logging.Logger, level: int, message: str, extra: Dict[str, Any] = None) -> None:
    """
    Логирует сообщение с дополнительными полями.

    Args:
        logger: Logger instance
        level: Уровень логирования (logging.INFO, etc.)
        message: Сообщение для логирования
        extra: Дополнительные поля для добавления в JSON
    """
    if extra:
        logger.log(level, message, extra={"extra_fields": extra})
    else:
        logger.log(level, message)
